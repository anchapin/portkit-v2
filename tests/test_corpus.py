"""The real-mod corpus (#21): a pinned manifest, downloaded jars, nothing committed."""
import hashlib
import io
import json

import pytest

from portkit import cli, corpus

PAYLOAD = b"PK\x05\x06" + b"\x00" * 18  # an empty zip, as far as anyone checks
SHA = hashlib.sha512(PAYLOAD).hexdigest()


def _mod(**over):
    entry = dict(name="m", project="p", version_id="v", url="https://example.invalid/m.jar",
                 sha512=SHA, license="MIT")
    entry.update(over)
    return corpus.Mod(**entry)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(body, calls):
    def opener(request, timeout):
        calls.append(request.full_url)
        return _Response(body)
    return opener


def test_the_committed_manifest_pins_every_mod():
    mods = corpus.load()
    assert len(corpus.select(mods)) >= 10  # #21's done-when, in the default set alone
    for mod in mods:
        assert mod.url.startswith("https://cdn.modrinth.com/data/")
        assert mod.version_id in mod.url
        assert len(mod.sha512) == 128 and int(mod.sha512, 16) >= 0
        assert mod.license and mod.source
    assert not list((corpus.ROOT / "fixtures" / "real").glob("*.jar"))  # never committed


def test_baseline_covers_exactly_the_manifest():
    baseline = json.loads((corpus.ROOT / "fixtures" / "real" / "coverage-baseline.json").read_text())
    assert set(baseline["fixtures"]) == {m.name for m in corpus.load()}
    assert all("errors" in entry for entry in baseline["fixtures"].values())


def test_tinkers_is_optional_and_mythic_metals_replaces_it():
    """2026-10-12: Tinkers' 11,752 tool sprites made it a file-count outlier (#122)."""
    mods = {m.name: m for m in corpus.load()}
    default = {m.name for m in corpus.select(list(mods.values()))}
    assert "mythicmetals" in default
    assert {"tinkers_construct", "alexs_mobs", "mekanism"} <= {n for n, m in mods.items() if m.optional}
    assert not default & {"tinkers_construct", "alexs_mobs", "mekanism"}


def test_select_skips_optional_mods_unless_asked(tmp_path):
    mods = [_mod(name="a"), _mod(name="b", optional=True), _mod(name="c")]
    assert [m.name for m in corpus.select(mods)] == ["a", "c"]
    assert [m.name for m in corpus.select(mods, include_optional=True)] == ["a", "b", "c"]
    assert [m.name for m in corpus.select(mods, ["b"])] == ["b"]  # named: optional or not
    with pytest.raises(corpus.CorpusError, match="not in the corpus manifest: zz"):
        corpus.select(mods, ["zz"])


def _manifest(tmp_path, *entries):
    text = ""
    for name, optional in entries:
        text += (f'[[mod]]\nname="{name}"\nproject="p"\nversion_id="v"\nurl="u"\n'
                 f'sha512="{SHA}"\nlicense="MIT"\n' + ("optional = true\n" if optional else "") + "\n")
    path = tmp_path / "mods.toml"
    path.write_text(text)
    return path


def test_optional_must_be_a_bool(tmp_path):
    path = _manifest(tmp_path, ("x", False))
    path.write_text(path.read_text() + 'optional = "yes"\n')
    with pytest.raises(corpus.CorpusError, match="optional must be true or false"):
        corpus.load(path)


def test_corpus_list_and_fetch_skip_optional_mods(tmp_path, monkeypatch, capsys):
    manifest = _manifest(tmp_path, ("main", False), ("extra", True))
    cache = tmp_path / "cache"
    monkeypatch.setenv("PORTKIT_CORPUS_CACHE", str(cache))
    for name in ("main", "extra"):  # pre-seed the cache so fetch never downloads
        cache.mkdir(exist_ok=True)
        (cache / f"{name}-{SHA[:12]}.jar").write_bytes(PAYLOAD)
    assert cli.main(["corpus", "list", "--manifest", str(manifest)]) == 0
    out = capsys.readouterr().out
    assert "main" in out and "default" in out and "1 optional, not shown: extra" in out
    assert cli.main(["corpus", "list", "--manifest", str(manifest), "--include-optional"]) == 0
    assert "optional" in capsys.readouterr().out
    assert cli.main(["corpus", "fetch", "--manifest", str(manifest)]) == 0
    out = capsys.readouterr().out
    assert "cached  main" in out and "cached  extra" not in out and "skipped 1 optional: extra" in out
    assert cli.main(["corpus", "fetch", "--manifest", str(manifest), "--fixture", "extra"]) == 0
    assert "cached  extra" in capsys.readouterr().out


def test_eval_corpus_ignores_and_keeps_skipped_optional_baselines(tmp_path, monkeypatch, capsys):
    """A skipped optional mod is neither 'missing from the corpus' nor dropped
    from the baseline when the default set is re-banked."""
    import zipfile

    manifest = _manifest(tmp_path, ("main", False), ("extra", True))
    jar = tmp_path / "main.jar"
    with zipfile.ZipFile(jar, "w") as zf:
        zf.writestr("fabric.mod.json", json.dumps({"id": "main", "version": "1"}))
        zf.writestr("assets/main/lang/en_us.json", json.dumps({"item.main.thing": "Thing"}))
    monkeypatch.setattr(corpus, "cached", lambda mod, cache=None: jar if mod.name == "main" else None)
    extra = {"coverage": 5.0, "files": 9, "residue": 3, "errors": 2}
    baseline = tmp_path / "coverage-baseline.json"
    baseline.write_text(json.dumps({"fixtures": {"extra": extra}}))
    args = ["eval", "--corpus", "--manifest", str(manifest), "--baseline", str(baseline)]
    assert cli.main(args) == 0, capsys.readouterr().out
    assert "missing from the corpus" not in capsys.readouterr().out
    assert cli.main(args + ["--update-baseline"]) == 0
    banked = json.loads(baseline.read_text())["fixtures"]
    assert banked["extra"] == extra and "main" in banked
    # Asked for, the optional mod has to be there.
    assert cli.main(args + ["--include-optional"]) == 2
    assert "not in the corpus cache: extra" in capsys.readouterr().err


def test_manifest_errors_are_named(tmp_path):
    bad = tmp_path / "mods.toml"
    bad.write_text('[[mod]]\nname = "x"\nproject = "p"\n')
    with pytest.raises(corpus.CorpusError, match="missing version_id"):
        corpus.load(bad)
    bad.write_text(f'[[mod]]\nname="x"\nproject="p"\nversion_id="v"\nurl="u"\nsha512="{SHA}"\n'
                   'license="MIT"\nlicence="typo"\n')
    with pytest.raises(corpus.CorpusError, match="unknown key"):
        corpus.load(bad)


def test_fetch_verifies_and_caches(tmp_path):
    calls = []
    path, downloaded = corpus.fetch(_mod(), tmp_path, opener=_opener(PAYLOAD, calls))
    assert downloaded and path.read_bytes() == PAYLOAD
    assert path.name == f"m-{SHA[:12]}.jar"
    again, downloaded = corpus.fetch(_mod(), tmp_path, opener=_opener(PAYLOAD, calls))
    assert again == path and not downloaded and len(calls) == 1


def test_a_changed_upstream_file_is_refused(tmp_path):
    with pytest.raises(corpus.CorpusError, match="sha512 mismatch"):
        corpus.fetch(_mod(), tmp_path, opener=_opener(b"something else", []))
    assert not list(tmp_path.iterdir())  # no partial left behind
    # A corrupted cache entry is not trusted either.
    _mod().path(tmp_path).write_bytes(b"corrupt")
    assert corpus.cached(_mod(), tmp_path) is None


def test_eval_corpus_without_the_jars_says_how_to_get_them(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PORTKIT_CORPUS_CACHE", str(tmp_path))
    assert cli.main(["eval", "--corpus"]) == 2
    assert "portkit corpus fetch" in capsys.readouterr().err


@pytest.mark.realmods
def test_real_corpus_at_or_above_baseline(capsys):
    """The default set; runs only where its jars are cached (the nightly job),
    skipped offline. Optional mods need not be cached."""
    missing = [m.name for m in corpus.select(corpus.load()) if corpus.cached(m) is None]
    if missing:
        pytest.skip(f"real mods not cached: {', '.join(missing)} (portkit corpus fetch)")
    assert cli.main(["eval", "--corpus"]) == 0, capsys.readouterr().out


@pytest.mark.realmods
def test_optional_corpus_at_or_above_baseline(capsys):
    """The optional mods (Tinkers, Alex's Mobs, Mekanism): run only where they are
    cached (`portkit corpus fetch --include-optional`); never required."""
    optional = [m for m in corpus.load() if m.optional]
    missing = [m.name for m in optional if corpus.cached(m) is None]
    if missing:
        pytest.skip(f"optional mods not cached: {', '.join(missing)} "
                    "(portkit corpus fetch --include-optional)")
    args = ["eval", "--corpus"] + [a for m in optional for a in ("--fixture", m.name)]
    assert cli.main(args) == 0, capsys.readouterr().out
