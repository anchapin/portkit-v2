"""Every staged resource file is either converted or reported. No third option."""
import json
import zipfile

import pytest

from portkit.pipeline import convert, unowned


def stage(tmp_path, files: dict[str, str]):
    root = tmp_path / "mod"
    for rel, body in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return root


def test_unowned_groups_by_directory(tmp_path):
    root = stage(tmp_path, {
        "assets/ex/models/block/a.json": "{}",
        "assets/ex/models/block/b.json": "{}",
        "assets/ex/models/item/c.json": "{}",
        "assets/ex/blockstates/a.json": "{}",
        "data/ex/tags/blocks/t.json": "{}",
    })
    items = unowned(root, consumed=set())
    by_source = {u.source: u.count for u in items}
    assert by_source == {
        "assets/ex/blockstates/": 1,
        "assets/ex/models/": 3,
        "data/ex/tags/": 1,
    }
    assert all(u.kind == "unowned" for u in items)


def test_consumed_files_are_not_reported(tmp_path):
    root = stage(tmp_path, {
        "assets/ex/lang/en_us.json": "{}",
        "assets/ex/models/block/a.json": "{}",
    })
    items = unowned(root, consumed={"assets/ex/lang/en_us.json"})
    assert [u.source for u in items] == ["assets/ex/models/"]


def test_real_conversion_accounts_for_every_resource_file(tmp_path, fixtures_dir):
    source = fixtures_dir / "simple_block_mod" / "input"
    staged = sum(1 for p in source.rglob("*") if p.is_file())
    result = convert(source, tmp_path / "out")
    # nothing in this fixture is unowned, and the books still balance
    assert [u for u in result.unhandled if u.kind == "unowned"] == []
    assert result.residue_count == 0
    assert result.coverage == 100.0
    assert staged > 0


def test_unowned_files_drag_coverage_down(tmp_path, fixtures_dir):
    source = tmp_path / "mod"
    for item in (fixtures_dir / "simple_block_mod" / "input").rglob("*"):
        if item.is_file():
            rel = item.relative_to(fixtures_dir / "simple_block_mod" / "input")
            target = source / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())
    for i in range(10):
        m = source / "assets" / "examplemod" / "models" / "block" / f"m{i}.json"
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text("{}")

    result = convert(source, tmp_path / "out")
    unowned_items = [u for u in result.unhandled if u.kind == "unowned"]
    assert [u.count for u in unowned_items] == [10]
    assert result.residue_count == 10
    assert result.coverage < 100.0
    # one entry, ten files: the entry count must not be what coverage uses
    assert len(unowned_items) == 1


def test_summary_reports_files_not_entries(tmp_path, fixtures_dir):
    source = tmp_path / "mod"
    for item in (fixtures_dir / "simple_block_mod" / "input").rglob("*"):
        if item.is_file():
            rel = item.relative_to(fixtures_dir / "simple_block_mod" / "input")
            target = source / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())
    # advancements: a lane no converter claims yet, so these group as unowned
    (source / "data" / "examplemod" / "advancements").mkdir(parents=True)
    for i in range(3):
        (source / "data" / "examplemod" / "advancements" / f"a{i}.json").write_text("{}")

    summary = convert(source, tmp_path / "out").summary()
    assert summary["unhandled"] == 1
    assert summary["unhandled_files"] == 3
    assert summary["coverage"] < 100.0


def test_jar_classes_count_as_the_files_they_are(tmp_path, fixtures_dir):
    jar = tmp_path / "mod.jar"
    source = fixtures_dir / "simple_block_mod" / "input"
    with zipfile.ZipFile(jar, "w") as zf:
        for item in sorted(source.rglob("*")):
            if item.is_file():
                zf.write(item, item.relative_to(source).as_posix())
        for i in range(12):
            zf.writestr(f"com/example/C{i}.class", b"\xca\xfe\xba\xbe")

    result = convert(jar, tmp_path / "out")
    java = [u for u in result.unhandled if u.kind == "java_code"]
    assert [u.count for u in java] == [12]
    assert result.residue_count == 12
