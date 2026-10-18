"""Registration names built by concatenation (#280, portkit.blockcode).

The class files under tests/data/concatcode are javac 21 output (build.sh):
an example mod whose modules hand a wood's name to a helper that appends
"_planks" / "_pressure_plate" (makeConcatWithConstants and StringBuilder),
loop over a mod enum, a static final array, an int and DyeColor.values(),
and an example library (../libcode/lib plus a creative-tab "chain" whose
start/end a stopped run leaves half done, Zeta's CreativeTabManager shape).
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from portkit import blockcode, libraries
from portkit.blockcode import Arr, Machine, Obj, _format, _name_pieces, _recipe_matcher
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "concatcode"
COLORS = ("white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray",
          "cyan", "purple", "blue", "brown", "green", "red", "black")
READ = {
    "maple_planks": "com/example/lib/LibBlock",
    "maple_pressure_plate": "com/example/lib/LibPlateBlock",
    "stripped_maple_log": "com/example/lib/LibBlock",
    "ruby_lamp": "com/example/lib/LibBlock",
    "sapphire_lamp": "com/example/lib/LibBlock",
    "slate_tiles": "com/example/lib/LibBlock",
    "marble_tiles": "com/example/lib/LibBlock",
    "tier_0_true_crate": "com/example/lib/LibBlock",
    "tier_1_false_crate": "com/example/lib/LibBlock",
    **{f"{c}_stool": "com/example/concat/StoolBlock" for c in COLORS},
}
UNREAD = ["odd_1.5_block", "null_block", "onyx_ruby", "maple_null"]


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _index() -> ClassIndex:
    return ClassIndex(_entries(DATA / "classes"), _entries(DATA / "library"))


def _read(names):
    _machine, reg = blockcode._registered(_index(), list(names))
    return reg


def test_concatenated_names_are_evaluated_from_the_bytecode():
    reg = _read([*READ, *UNREAD])
    for name, cls in READ.items():
        objs, why = reg[name]
        assert objs and objs[0].cls == cls, (name, why)


def test_a_name_that_cant_be_evaluated_is_left_unread_never_guessed():
    reg = _read([*READ, *UNREAD])
    # A float's text (Java's Float.toString isn't Python's), an unknown
    # call's result, and a name only a run on an unknown argument would make.
    for name in ("odd_1.5_block", "null_block", "maple_null"):
        objs, why = reg[name]
        assert objs == [] and why == "no registration of this block was found in the mod's classes"


def test_a_concatenated_name_given_a_non_block_is_not_a_reason():
    objs, why = _read(["onyx_ruby", "maple_planks"])["onyx_ruby"]
    assert objs == [] and "LibModule" not in why
    assert why == "no registration of this block was found in the mod's classes"


def test_dye_colour_loop_through_a_caller_reads_all_sixteen():
    reg = _read([f"{c}_stool" for c in COLORS])
    assert all(reg[f"{c}_stool"][0] for c in COLORS)


def test_a_stopped_run_does_not_leave_its_statics_half_done():
    # BrokenModule (run first: classes run in name order) starts the
    # library's chain and stops part way; MapleModule's helper starts a chain
    # too, which ends a chain left open by walking a list it can't know.
    index = _index()
    assert index.names().index("com/example/concat/BrokenModule") < \
        index.names().index("com/example/concat/MapleModule")
    assert _read(["maple_planks"])["maple_planks"][0]


def test_whole_names_still_read_as_before_without_concatenation():
    # The libcode fixture (whole names as ldc constants) is unchanged.
    from tests.test_libraries import DATA as LIBDATA, NAMES
    index = ClassIndex(_entries(LIBDATA / "classes"), _entries(LIBDATA / "library"))
    _machine, reg = blockcode._registered(index, NAMES)
    assert all(reg[n][0] for n in NAMES)


# --- the pieces ---------------------------------------------------------------

def test_name_pieces_are_whole_word_runs_short_of_the_name():
    assert _name_pieces({"azalea_pressure_plate"}) == {
        "azalea", "pressure", "plate", "azalea_pressure", "pressure_plate"}
    assert _name_pieces({"quark:lamp"}) == set()


def test_recipe_matcher_needs_a_whole_name():
    pat = _recipe_matcher("\x01_pressure_plate")
    assert pat.fullmatch("oak_pressure_plate")
    assert not pat.fullmatch("_pressure_plate")
    assert not _recipe_matcher("quark:building/\x01_slab").fullmatch("oak_slab")


def test_string_format_only_plain_s():
    assert _format(["%s_slab", Arr(["oak"])]) == "oak_slab"
    assert _format(["%s:%s", Arr(["quark", "x"])]) == "quark:x"
    assert _format(["100%%_%s", Arr(["a"])]) == "100%_a"
    assert _format(["%d_slab", Arr([3])]) is blockcode.UNKNOWN
    assert _format(["%s_slab", Arr([blockcode.UNKNOWN])]) is blockcode.UNKNOWN


def test_stringify_follows_the_descriptor():
    m = Machine(ClassIndex({}))
    assert m.stringify(97, "C") == "a"
    assert m.stringify(1, "Z") == "true" and m.stringify(0, "Z") == "false"
    assert m.stringify(7, "I") == "7"
    assert m.stringify(1.5, "F") is None
    assert m.stringify("x") == "x"
    assert m.stringify(Obj("com/x/Unseen", {"__enum_name": "RUBY"})) is None  # not the mod's: toString unknown
    assert m.stringify(blockcode.UNKNOWN) is None


def test_nested_library_jars_over_the_cap_are_skipped(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as iz:
        iz.writestr("com/x/Inner.class", b"\xca\xfe")
    jar = tmp_path / "lib.jar"
    with zipfile.ZipFile(jar, "w") as zf:
        zf.writestr("com/x/Outer.class", b"\xca\xfe")
        zf.writestr("META-INF/jars/inner.jar", buf.getvalue())
    assert set(libraries.classes(jar)) == {"com/x/Outer", "com/x/Inner"}
    monkeypatch.setattr(libraries, "_MAX_NESTED_JAR_BYTES", 10)
    assert set(libraries.classes(jar)) == {"com/x/Outer"}


def test_case_change_only_with_a_known_locale():
    m = Machine(ClassIndex({}))
    desc = "(Ljava/util/Locale;)Ljava/lang/String;"
    assert m._strings("java/lang/String", "toLowerCase", desc, "RUBY",
                      [blockcode.Const("java/util/Locale", "ROOT")], False) == ["ruby"]
    assert m._strings("java/lang/String", "toLowerCase", desc, "RUBY",
                      [Obj("java/util/Locale")], False) == [blockcode.UNKNOWN]
    assert m._strings("java/lang/String", "toLowerCase", "()Ljava/lang/String;", "RUBY", [], False) == ["ruby"]


def test_dye_colours_are_vanilla_names():
    m = Machine(ClassIndex({}))
    (arr,) = m._strings(blockcode._DYE_COLOR, "values", "()[Lnet/minecraft/world/item/DyeColor;", None, [], True)
    got = [m._strings(blockcode._DYE_COLOR, "getSerializedName", "()Ljava/lang/String;", c, [], False)[0]
           for c in arr.items]
    assert tuple(got) == COLORS
