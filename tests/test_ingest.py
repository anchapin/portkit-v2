import json
import zipfile
from pathlib import Path

import pytest

from portkit.ingest import IngestError, from_jar, ingest
from portkit.pipeline import convert


def build_jar(path: Path, source: Path, *, classes=2, nested=False, metadata=True) -> Path:
    """Wrap a fixture input tree the way a real Forge/Fabric jar ships it."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(source.rglob("*")):
            if item.is_file():
                zf.write(item, item.relative_to(source).as_posix())
        for i in range(classes):
            zf.writestr(f"com/example/examplemod/Thing{i}.class", b"\xca\xfe\xba\xbe")
        if metadata:
            zf.writestr("fabric.mod.json", json.dumps({"id": "examplemod", "version": "1.0.0"}))
        if nested:
            zf.writestr("META-INF/jars/somelib-1.2.jar", b"PK\x03\x04nested")
    return path


@pytest.fixture
def mod_jar(tmp_path, fixtures_dir):
    return build_jar(tmp_path / "examplemod-1.0.0.jar", fixtures_dir / "simple_block_mod" / "input")


def test_jar_stages_resource_lanes(mod_jar, tmp_path):
    staged = from_jar(mod_jar, tmp_path / "staging")
    assert staged.namespace == "examplemod"
    assert (staged.root / "assets/examplemod/lang/en_us.json").is_file()
    assert (staged.root / "data/examplemod/recipes/copper_block.json").is_file()


def test_class_files_are_not_extracted_but_are_counted(mod_jar, tmp_path):
    staged = from_jar(mod_jar, tmp_path / "staging")
    assert list(staged.root.rglob("*.class")) == []
    assert staged.class_count == 2
    residue = staged.residue()
    assert [u.kind for u in residue] == ["java_code"]
    assert "bytecode" in residue[0].reason


def test_loader_metadata_is_kept_for_later(mod_jar, tmp_path):
    staged = from_jar(mod_jar, tmp_path / "staging")
    assert json.loads(staged.metadata["fabric.mod.json"])["id"] == "examplemod"


def test_nested_jars_are_reported_not_silently_dropped(tmp_path, fixtures_dir):
    jar = build_jar(
        tmp_path / "withlib.jar", fixtures_dir / "simple_block_mod" / "input", nested=True
    )
    staged = from_jar(jar, tmp_path / "staging")
    kinds = [u.kind for u in staged.residue()]
    assert "nested_jar" in kinds


def test_extra_namespaces_are_reported(tmp_path, fixtures_dir):
    source = tmp_path / "multi"
    for item in sorted((fixtures_dir / "simple_block_mod" / "input").rglob("*")):
        if item.is_file():
            rel = item.relative_to(fixtures_dir / "simple_block_mod" / "input")
            target = source / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())
    extra = source / "assets" / "otherns" / "lang" / "en_us.json"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("{}")
    jar = build_jar(tmp_path / "multi.jar", source, classes=0)
    staged = from_jar(jar, tmp_path / "staging")
    assert staged.namespace == "examplemod"
    assert [u.source for u in staged.residue() if u.kind == "extra_namespace"] == ["otherns"]


def test_zip_slip_members_are_refused(tmp_path, fixtures_dir):
    jar = tmp_path / "evil.jar"
    with zipfile.ZipFile(jar, "w") as zf:
        zf.writestr("assets/examplemod/lang/en_us.json", "{}")
        zf.writestr("../../../etc/portkit-pwned", "nope")
        zf.writestr("/tmp/portkit-pwned", "nope")
    staged = from_jar(jar, tmp_path / "staging")
    assert not (tmp_path / "etc").exists()
    assert not Path("/tmp/portkit-pwned").exists()
    assert staged.namespace == "examplemod"


def test_jar_without_resources_is_an_error(tmp_path):
    jar = tmp_path / "codeonly.jar"
    with zipfile.ZipFile(jar, "w") as zf:
        zf.writestr("com/example/Main.class", b"\xca\xfe\xba\xbe")
    with pytest.raises(IngestError, match="nothing to convert"):
        from_jar(jar, tmp_path / "staging")


def test_non_zip_is_an_error(tmp_path):
    fake = tmp_path / "notajar.jar"
    fake.write_text("hello")
    with pytest.raises(IngestError, match="not a jar"):
        from_jar(fake, tmp_path / "staging")


def test_directory_and_jar_convert_identically(mod_jar, tmp_path, fixtures_dir):
    from_dir = convert(fixtures_dir / "simple_block_mod" / "input", tmp_path / "out-dir")
    from_jar_ = convert(mod_jar, tmp_path / "out-jar")

    assert from_jar_.namespace == from_dir.namespace
    assert from_jar_.file_count == from_dir.file_count
    assert from_jar_.report.ok

    dir_files = {p.relative_to(from_dir.tree) for p in from_dir.tree.rglob("*") if p.is_file()}
    jar_files = {p.relative_to(from_jar_.tree) for p in from_jar_.tree.rglob("*") if p.is_file()}
    assert jar_files - {Path("unhandled.json")} == dir_files

    # The jar carries compiled code, so it honestly reports residue the directory has not got.
    assert [u.kind for u in from_jar_.unhandled] == ["java_code"]
    assert from_dir.unhandled == []


def test_ingest_accepts_either_shape(mod_jar, tmp_path, fixtures_dir):
    assert ingest(mod_jar, tmp_path / "s1").namespace == "examplemod"
    assert ingest(fixtures_dir / "simple_block_mod" / "input", tmp_path / "s2").namespace == "examplemod"
