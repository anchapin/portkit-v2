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
    assert len(mods) >= 3
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
    """Runs only where the jars are cached (the nightly job); skipped offline."""
    missing = [m.name for m in corpus.load() if corpus.cached(m) is None]
    if missing:
        pytest.skip(f"real mods not cached: {', '.join(missing)} (portkit corpus fetch)")
    assert cli.main(["eval", "--corpus"]) == 0, capsys.readouterr().out
