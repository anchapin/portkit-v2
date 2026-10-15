"""portkit schemas check|refresh (#155): offline, against a fake registry document and tarball."""
import base64
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

from portkit import cli
from portkit.validate import schema
from portkit.validate import schema_upstream as up

ROOT = Path(__file__).resolve().parents[1]
COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


def _tgz(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"package/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _integrity(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def _packument(versions: dict[str, bytes | None], times: dict[str, str] | None = None) -> dict:
    out = {"versions": {}, "time": {}}
    for i, (v, tgz) in enumerate(versions.items()):
        dist = {"tarball": f"https://example.invalid/{v}.tgz"}
        if tgz is not None:
            dist["integrity"] = _integrity(tgz)
        out["versions"][v] = {"gitHead": COMMIT_B if i % 2 else COMMIT_A, "dist": dist}
        out["time"][v] = (times or {}).get(v, f"2026-10-{10 + i:02d}T12:00:00.000Z")
    return out


def _components(*names):
    return json.dumps({"properties": {n: {} for n in names}})


def _package(*components, extra=None):
    files = {
        "LICENSE": "MIT new",
        "schemas/bp/blocks/block_components.schema.json": _components(*components),
        "schemas/bp/blocks/index.schema.json": '{"$ref": "../../common/floatrange.schema.json"}',
        "schemas/bp/items/index.schema.json": '{"type": "object", "x": "../../common/not_a_ref.json"}',
        "schemas/common/floatrange.schema.json": '{"type": "number"}',
        "schemas/common/unused.schema.json": "{}",
        "schemas/rp/ignored.json": "{}",
    }
    files.update(extra or {})
    return _tgz(files)


@pytest.fixture
def vendored(tmp_path):
    """A one-snapshot schemas root with its SOURCE.md, vendored from a beta."""
    root = tmp_path / "schemas"
    snap = root / "1.26.60"
    (snap / "bp/blocks").mkdir(parents=True)
    (snap / "bp/items").mkdir(parents=True)
    (snap / "common").mkdir()
    (snap / "bp/blocks/block_components.schema.json").write_text(_components("minecraft:geometry", "minecraft:old"))
    (snap / "bp/blocks/index.schema.json").write_text('{"$ref": "../../common/floatrange.schema.json"}')
    (snap / "bp/blocks/gone.schema.json").write_text("{}")
    (snap / "bp/items/index.schema.json").write_text('{"type": "object", "x": "../../common/not_a_ref.json"}')
    (snap / "common/floatrange.schema.json").write_text('{"type": "number"}')
    (snap / "LICENSE").write_text("MIT old")
    source = root / "SOURCE.md"
    source.write_text(
        "# x\n\n| snapshot dir | package version | upstream commit (`gitHead`) | npm published |\n"
        "| --- | --- | --- | --- |\n"
        f"| `1.26.60/` | `@minecraft/bedrock-schemas` 1.26.60-beta.24 | `{'f' * 40}` | 2026-09-30 |\n\ntail\n"
    )
    return root, source


# -- versions ---------------------------------------------------------------
def test_versions_parse_and_order_like_semver():
    assert up.parse_version("1.26.60-beta.24") == ((1, 26, 60), "beta.24")
    assert up.is_stable("1.26.60") and not up.is_stable("1.26.60-beta.2")
    ordered = sorted(["1.26.60", "1.26.60-beta.10", "1.26.50", "1.26.60-beta.9"], key=up._sort_key)
    assert ordered == ["1.26.50", "1.26.60-beta.9", "1.26.60-beta.10", "1.26.60"]
    with pytest.raises(up.SchemaUpstreamError):
        up.parse_version("latest")


# -- SOURCE.md ------------------------------------------------------------------
def test_the_committed_source_table_has_a_row_for_every_snapshot():
    rows = up.pins()
    assert [r.snapshot for r in rows] == [".".join(map(str, s)) for s in schema.SNAPSHOTS]
    for row in rows:
        assert up.parse_version(row.version)[0] == up.parse_version(row.snapshot)[0]
        assert (schema.SCHEMA_ROOT / row.snapshot / "bp/blocks/block_components.schema.json").is_file()
        assert (schema.SCHEMA_ROOT / row.snapshot / "LICENSE").is_file()


def test_a_source_table_without_rows_is_an_error(tmp_path):
    (tmp_path / "S.md").write_text("no table")
    with pytest.raises(up.SchemaUpstreamError):
        up.pins(tmp_path / "S.md")


# -- check -------------------------------------------------------------------
def test_waiting_while_only_prereleases_of_the_snapshot_exist(vendored):
    _, source = vendored
    pk = _packument({"1.26.50": None, "1.26.60-beta.24": None, "1.26.60-beta.28": None})
    [st] = up.check(pk, source)
    assert st.state == "waiting" and not st.action_needed
    assert (st.latest_stable, st.newest_prerelease, st.stable) == ("1.26.50", "1.26.60-beta.28", None)
    assert "no stable 1.26.60 yet" in st.message()


def test_refresh_due_once_the_stable_package_is_out(vendored):
    _, source = vendored
    pk = _packument({"1.26.60-beta.28": None, "1.26.60": None})
    [st] = up.check(pk, source)
    assert st.state == "refresh" and st.action_needed and st.stable == "1.26.60"
    assert "REFRESH DUE" in st.message()


def test_current_when_the_stable_package_is_vendored_and_a_newer_one_is_reported():
    pin = up.Pin("1.26.60", "1.26.60", COMMIT_A, "2026-10-27")
    st = up.status(pin, _packument({"1.26.60": None, "1.26.70-beta.1": None, "1.26.70": None}))
    assert st.state == "current" and not st.action_needed
    assert st.newer_stable == "1.26.70" and "new snapshot" in st.message()


# -- refresh -------------------------------------------------------------------
def test_refresh_mirrors_bp_copies_referenced_common_and_rewrites_the_row(vendored):
    root, source = vendored
    tgz = _package("minecraft:geometry", "minecraft:new")
    pk = _packument({"1.26.60-beta.24": None, "1.26.60": tgz}, {"1.26.60": "2026-10-27T17:00:00.000Z"})
    result = up.refresh_from_registry("1.26.60", None, pk, tarball=tgz, root=root, source_md=source)
    snap = root / "1.26.60"
    assert result.new_version == "1.26.60" and result.old_version == "1.26.60-beta.24"
    assert result.components_added == ["minecraft:new"] and result.components_removed == ["minecraft:old"]
    assert result.removed == ["bp/blocks/gone.schema.json"] and not (snap / "bp/blocks/gone.schema.json").exists()
    assert "LICENSE" in result.changed and (snap / "LICENSE").read_text() == "MIT new"
    assert result.common_copied == ["common/floatrange.schema.json"] and result.common_missing == []
    assert not (snap / "common/unused.schema.json").exists() and not (snap / "rp").exists()
    [pin] = up.pins(source)
    assert pin == up.Pin("1.26.60", "1.26.60", COMMIT_B, "2026-10-27")
    assert source.read_text().endswith("\n\ntail\n")
    # a second run against the same package changes nothing
    again = up.refresh_from_registry("1.26.60", None, pk, tarball=tgz, root=root, source_md=source)
    assert (again.added, again.removed, again.changed) == ([], [], [])


def test_dry_run_reports_and_writes_nothing(vendored):
    root, source = vendored
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    tgz = _package("minecraft:geometry")
    pk = _packument({"1.26.60": tgz})
    result = up.refresh_from_registry("1.26.60", None, pk, tarball=tgz, root=root, source_md=source, dry_run=True)
    assert result.dry_run and result.components_removed == ["minecraft:old"]
    assert "would re-vendor" in result.lines()[0]
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_no_stable_release_means_no_default_refresh(vendored):
    root, source = vendored
    pk = _packument({"1.26.60-beta.28": _package("minecraft:geometry")})
    with pytest.raises(up.SchemaUpstreamError, match="no stable .* 1.26.60 yet .*1.26.60-beta.28"):
        up.refresh_from_registry("1.26.60", None, pk, root=root, source_md=source)


def test_a_prerelease_needs_allow_prerelease(vendored):
    root, source = vendored
    tgz = _package("minecraft:geometry")
    pk = _packument({"1.26.60-beta.28": tgz})
    with pytest.raises(up.SchemaUpstreamError, match="prerelease"):
        up.refresh_from_registry("1.26.60", "1.26.60-beta.28", pk, tarball=tgz, root=root, source_md=source)
    result = up.refresh_from_registry("1.26.60", "1.26.60-beta.28", pk, tarball=tgz, root=root,
                                      source_md=source, allow_prerelease=True)
    assert up.pins(source)[0].version == "1.26.60-beta.28" and result.new_version == "1.26.60-beta.28"


def test_another_versions_package_is_a_new_snapshot_not_a_refresh(vendored):
    root, source = vendored
    tgz = _package("minecraft:geometry")
    with pytest.raises(up.SchemaUpstreamError, match="new snapshot"):
        up.refresh_from_registry("1.26.60", "1.26.70", _packument({"1.26.70": tgz}), tarball=tgz,
                                 root=root, source_md=source)


def test_a_tarball_that_does_not_match_the_registry_hash_is_refused(vendored):
    root, source = vendored
    pk = _packument({"1.26.60": _package("minecraft:geometry")})
    with pytest.raises(up.SchemaUpstreamError, match="sha512"):
        up.refresh_from_registry("1.26.60", None, pk, tarball=_package("minecraft:other"),
                                 root=root, source_md=source)
    assert up.pins(source)[0].version == "1.26.60-beta.24"


def test_a_package_without_block_schemas_is_refused(vendored):
    root, source = vendored
    tgz = _tgz({"LICENSE": "x", "schemas/bp/items/index.schema.json": "{}"})
    with pytest.raises(up.SchemaUpstreamError, match="bp/blocks"):
        up.refresh_from_registry("1.26.60", None, _packument({"1.26.60": tgz}), tarball=tgz,
                                 root=root, source_md=source)


def test_fetch_tarball_downloads_and_verifies():
    tgz = _package("minecraft:geometry")
    pk = _packument({"1.26.60": tgz})
    seen = []

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(request, timeout):
        seen.append(request.full_url)
        return _Resp(tgz)

    assert up.fetch_tarball(pk, "1.26.60", opener) == tgz
    assert seen == ["https://example.invalid/1.26.60.tgz"]

    def broken(request, timeout):
        return _Resp(b"tampered")

    with pytest.raises(up.SchemaUpstreamError):
        up.fetch_tarball(pk, "1.26.60", broken)


# -- the committed snapshot round-trips --------------------------------------------
def test_refreshing_the_committed_snapshot_from_its_own_files_changes_nothing(tmp_path):
    """The refresh layout matches the vendored tree: a package built from the
    committed files re-vendors byte-identically."""
    root = tmp_path / "schemas"
    shutil.copytree(schema.SCHEMA_ROOT, root)
    pin = up.pins(root / "SOURCE.md")[-1]
    snap = root / pin.snapshot
    files = {f"schemas/{p.relative_to(snap).as_posix()}": p.read_text(encoding="utf-8")
             for p in snap.rglob("*") if p.is_file() and p.name != "LICENSE"}
    files["LICENSE"] = (snap / "LICENSE").read_text(encoding="utf-8")
    tgz = _tgz(files)
    result = up.refresh(pin.snapshot, pin.version, tgz, pin.commit, pin.date, root=root,
                        source_md=root / "SOURCE.md", dry_run=True)
    assert (result.added, result.removed, result.changed) == ([], [], [])
    assert result.common_missing == ["common/expression.schema.json"]


# -- CLI -------------------------------------------------------------------------
def test_cli_check_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(up, "fetch_packument", lambda: _packument({"1.26.50": None, "1.26.60-beta.28": None}))
    assert cli.main(["schemas", "check"]) == 0
    assert "waiting" in capsys.readouterr().out
    monkeypatch.setattr(up, "fetch_packument", lambda: _packument({"1.26.60": None}))
    assert cli.main(["schemas", "check"]) == 1
    assert "REFRESH DUE" in capsys.readouterr().out

    def offline():
        raise up.SchemaUpstreamError("registry down")

    monkeypatch.setattr(up, "fetch_packument", offline)
    assert cli.main(["schemas", "check"]) == 2


def test_cli_refresh_without_a_stable_release_fails_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(up, "fetch_packument", lambda: _packument({"1.26.60-beta.28": None}))
    assert cli.main(["schemas", "refresh", "--dry-run"]) == 2
    assert "no stable" in capsys.readouterr().err
