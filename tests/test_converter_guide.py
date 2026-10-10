"""docs/converter-guide.md must keep working when followed literally (#23).

The guide's worked converter is lifted out of the markdown and run, so a change
to the converter contract that would break the guide breaks this test instead.
"""
import re
import types
from pathlib import Path

from portkit import converters
from portkit.model import SourceMod

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "converter-guide.md"


def _guide_converter():
    text = GUIDE.read_text()
    code = re.search(r"`src/portkit/converters/splashes.py`:\n\n```python\n(.*?)```", text, re.S).group(1)
    module = types.ModuleType("portkit.converters.splashes")
    module.__package__ = "portkit.converters"
    exec(compile(code, str(GUIDE), "exec"), module.__dict__)
    return module.convert


def _mod(tmp_path, splashes: bytes | None):
    (tmp_path / "assets" / "examplemod" / "lang").mkdir(parents=True)
    if splashes is not None:
        texts = tmp_path / "assets" / "minecraft" / "texts"
        texts.mkdir(parents=True)
        (texts / "splashes.txt").write_bytes(splashes)
    return SourceMod(root=tmp_path, namespace="examplemod")


def test_the_worked_example_converts_and_claims(tmp_path):
    result = _guide_converter()(_mod(tmp_path, b"Now on Bedrock!\nAlso try Java!\n\n"))
    assert result.files == {"splashes.json": {"canMerge": False, "splashes": ["Now on Bedrock!", "Also try Java!"]}}
    assert result.consumed == {"assets/minecraft/texts/splashes.txt"}
    assert result.unhandled == []


def test_the_worked_example_refuses_with_reasons(tmp_path):
    convert = _guide_converter()
    assert convert(_mod(tmp_path / "none", None)).files == {}
    empty = convert(_mod(tmp_path / "empty", b"\n\n"))
    assert [u.reason for u in empty.unhandled] == ["splashes.txt has no splash lines"]
    bad = convert(_mod(tmp_path / "bad", b"\xff\xfe"))
    assert [u.reason for u in bad.unhandled] == ["splashes.txt is not UTF-8"]


def test_the_example_is_still_an_exercise():
    """The guide says splashes land in unowned today; ship it and rewrite the guide."""
    assert not any(fn.__module__.endswith(".splashes") for fn in converters.CONVERTERS)
