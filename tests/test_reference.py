"""``portkit reference fetch``: Mojang's vanilla sound list, cached on demand (#124)."""
import hashlib
import io
import json

import pytest

from portkit import cli, data

UPSTREAM = json.dumps({"sound_definitions": {
    "random.bow": {"category": "neutral", "sounds": ["sounds/random/bow"]},
    "mob.slime.big": {"category": "hostile", "sounds": [
        {"name": "sounds/mob/slime/big1", "volume": 0.5}, "sounds/mob/slime/big1"]},
    "odd": {"sounds": [{"name": "elsewhere/x"}, 7]},
    "format_version": "1.14.0",
}}).encode()


def _opener(payload, calls=None):
    def opener(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        return io.BytesIO(payload)
    return opener


@pytest.fixture
def pinned(monkeypatch, tmp_path):
    """Pin the hash to what the fake upstream derives, with an empty cache."""
    digest = hashlib.sha256(data.derive_sounds(UPSTREAM).encode()).hexdigest()
    monkeypatch.setattr(data, "SOUNDS_SHA256", digest)
    monkeypatch.delenv("PORTKIT_VANILLA_SOUNDS", raising=False)
    cache = tmp_path / "cache"
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(cache))
    return cache


def test_nothing_from_bedrock_samples_is_vendored():
    assert not list((data.Path(data.__file__).parent).glob("*.gz"))
    assert not list((data.Path(data.__file__).parent).glob("*.txt"))


def test_the_url_is_pinned_to_the_commit():
    assert data.COMMIT in data.URL and data.URL.startswith("https://raw.githubusercontent.com/")
    assert len(data.SOUNDS_SHA256) == 64


def test_derive_keeps_sorted_unique_sounds_paths():
    lines = [l for l in data.derive_sounds(UPSTREAM).splitlines() if not l.startswith("#")]
    assert lines == ["sounds/mob/slime/big1", "sounds/random/bow"]


def test_fetch_verifies_caches_and_is_then_read(pinned):
    calls = []
    path, downloaded = data.fetch_sounds(opener=_opener(UPSTREAM, calls))
    assert downloaded and path.parent == pinned and data.SOUNDS_SHA256[:12] in path.name
    assert calls == [data.URL]
    assert data.fetch_sounds(opener=_opener(b"unused", calls)) == (path, False)
    assert len(calls) == 1
    assert data.bedrock_vanilla_sounds() == {"sounds/mob/slime/big1", "sounds/random/bow"}


def test_a_changed_upstream_is_refused_and_nothing_cached(pinned):
    changed = UPSTREAM.replace(b"random/bow", b"random/bow2")
    with pytest.raises(data.ReferenceDataError, match="sha256 mismatch"):
        data.fetch_sounds(opener=_opener(changed))
    assert not pinned.exists() or not any(pinned.iterdir())
    assert data.bedrock_vanilla_sounds() is None


def test_a_download_failure_is_named(pinned):
    def opener(request, timeout):
        raise OSError("no network")
    with pytest.raises(data.ReferenceDataError, match="download failed"):
        data.fetch_sounds(opener=opener)


def test_a_tampered_cache_counts_as_missing(pinned):
    path, _ = data.fetch_sounds(opener=_opener(UPSTREAM))
    path.write_text(path.read_text() + "sounds/extra\n")
    assert data.cached_sounds() is None
    assert data.bedrock_vanilla_sounds() is None


def test_the_cache_honours_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("PORTKIT_REFERENCE_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert data.cache_dir() == tmp_path / "portkit" / "reference"


def test_cli_reference_list_and_fetch(pinned, monkeypatch, capsys):
    assert cli.main(["reference", "list"]) == 0
    assert "missing" in capsys.readouterr().out
    real = data.fetch_sounds
    monkeypatch.setattr(data, "fetch_sounds", lambda cache=None: real(cache, opener=_opener(UPSTREAM)))
    assert cli.main(["reference", "fetch"]) == 0
    assert "fetched" in capsys.readouterr().out
    assert cli.main(["reference", "list"]) == 0
    assert "cached" in capsys.readouterr().out


def test_cli_reference_fetch_failure_exits_nonzero(pinned, monkeypatch, capsys):
    def boom(cache=None):
        raise data.ReferenceDataError("vanilla sound list: download failed")
    monkeypatch.setattr(data, "fetch_sounds", boom)
    assert cli.main(["reference", "fetch"]) == 1
    assert "FAILED" in capsys.readouterr().err
