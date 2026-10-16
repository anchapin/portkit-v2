"""Explained-empty (#279): a mod with nothing Bedrock can hold is reported, not packed."""
from __future__ import annotations

import json
import struct
import zipfile

from portkit import codeonly
from portkit.bytecode import ClassIndex
from portkit.gauntlet import classify
from portkit.model import Unhandled
from portkit.pipeline import convert
from portkit.validate import validate_tree


def _classfile(name: str, super_name: str = "java/lang/Object", interfaces=(), refs=(), strings=(),
               access: int = 0x21) -> bytes:
    """A minimal valid class file: ``refs`` are (owner, method) Methodrefs."""
    pool: list[bytes] = []
    index: dict[tuple, int] = {}

    def add(key, raw: bytes, wide: bool = False) -> int:
        if key in index:
            return index[key]
        pool.append(raw)
        index[key] = len(pool)
        return index[key]

    def utf(text: str) -> int:
        data = text.encode()
        return add(("utf", text), b"\x01" + struct.pack(">H", len(data)) + data)

    def cls(text: str) -> int:
        return add(("class", text), b"\x07" + struct.pack(">H", utf(text)))

    this, sup = cls(name), cls(super_name)
    ifaces = [cls(i) for i in interfaces]
    for owner, method in refs:
        nat = add(("nat", method), b"\x0c" + struct.pack(">HH", utf(method), utf("()V")))
        add(("mref", owner, method), b"\x0a" + struct.pack(">HH", cls(owner), nat))
    for text in strings:
        add(("str", text), b"\x08" + struct.pack(">H", utf(text)))
    out = b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 52, len(pool) + 1) + b"".join(pool)
    out += struct.pack(">HHH", access, this, sup) + struct.pack(">H", len(ifaces))
    out += b"".join(struct.pack(">H", i) for i in ifaces)
    return out + struct.pack(">HHH", 0, 0, 0)  # no fields, methods or attributes


def _jar(path, classes: dict[str, bytes], files: dict[str, str] | None = None, toml: bool = True):
    with zipfile.ZipFile(path, "w") as zf:
        if toml:
            zf.writestr("META-INF/neoforge.mods.toml",
                        'modLoader="javafml"\nloaderVersion="[1,)"\nlicense="MIT"\n'
                        '[[mods]]\nmodId="codemod"\nversion="1.2.3"\ndisplayName="Code Mod"\n'
                        '[[mixins]]\nconfig="codemod.mixins.json"\n')
            zf.writestr("codemod.mixins.json", json.dumps({"mixins": ["A", "B"], "client": ["C"]}))
        for name, data in classes.items():
            zf.writestr(name + ".class", data)
        for name, text in (files or {}).items():
            zf.writestr(name, text)
    return path


def _screen_mod(tmp_path, files=None):
    classes = {
        "com/ex/ConfigScreen": _classfile("com/ex/ConfigScreen", "net/minecraft/client/gui/screens/Screen"),
        "com/ex/Keys": _classfile("com/ex/Keys", refs=[
            ("net/minecraft/client/KeyMapping", "<init>"),
            ("net/neoforged/neoforge/client/event/RegisterKeyMappingsEvent", "register")]),
        "com/ex/Packet": _classfile("com/ex/Packet",
                                    interfaces=("net/minecraft/network/protocol/common/custom/CustomPacketPayload",)),
    }
    return _jar(tmp_path / "codemod.jar", classes, files)


def test_scan_reads_screens_keybinds_and_packets_from_bytecode(tmp_path):
    jar = _screen_mod(tmp_path)
    facts = codeonly.facts(jar)
    assert facts["screens"] == 1 and facts["key_registration"] == 1 and facts["payloads"] == 1
    assert facts["mixins"] == 3 and facts["client_mixins"] == 1
    got = {r["class"]: r for r in codeonly.reason_classes(facts)}
    assert {"mixin_patch", "gui_screen", "keybind", "networking"} <= set(got)
    assert all(r["bedrock"] and r["evidence"] for r in got.values())


def test_render_formats_from_strings_and_files(tmp_path):
    classes = {"com/ex/Loader": _classfile("com/ex/Loader", strings=["optifine/cem/", "model.jem"])}
    jar = _jar(tmp_path / "r.jar", classes, {"resourcepacks/default/assets/x/optifine/ctm/glass/0.png": "x",
                                             "assets/x/shaders/core/a.fsh": "x"})
    facts = codeonly.facts(jar)
    rc = {r["class"]: r for r in codeonly.reason_classes(facts)}
    text = " ".join(rc["client_rendering"]["evidence"])
    assert "CEM" in text and "CTM" in text and "shader file" in text and "built-in Java resource pack" in text


def test_code_only_jar_converts_to_explained_empty(tmp_path):
    jar = _screen_mod(tmp_path, files={
        "assets/codemod/lang/en_us.json": json.dumps({"screen.codemod.title": "Settings", "codemod.odd": "x"}),
        "assets/codemod/textures/gui/button.png": "png"})
    out = tmp_path / "out"
    res = convert(jar, out)
    assert res.outcome == codeonly.OUTCOME and res.file_count == 0
    assert not (out / "behavior_pack").exists() and not (out / "resource_pack").exists()
    assert res.addon is None and not list(out.glob("*.mcaddon"))
    assert res.report.ok and [f.rule for f in res.report.findings] == ["tree.explained_empty"]
    kinds = {u.kind for u in res.unhandled}
    assert kinds == {"java_code", "code_only"}
    lang = [u for u in res.unhandled if u.source.endswith("en_us.json")]
    assert len(lang) == 1 and "reason classes: mixin_patch" in lang[0].reason  # per-key lines folded
    doc = json.loads((out / codeonly.REPORT_NAME).read_text())
    assert doc["outcome"] == "explained-empty" and doc["mod"]["id"] == "codemod"
    assert [r["class"] for r in doc["reason_classes"]] == [r["class"] for r in res.reason_classes]
    summary = res.summary()
    assert summary["outcome"] == "explained-empty" and "gui_screen" in summary["reason_classes"]
    # The validator, run on its own over the tree, agrees.
    again = validate_tree(out)
    assert again.ok and again.findings[0].severity == "info"


def test_jar_without_assets_ingests_and_explains(tmp_path):
    """The five #278 ingest errors: no assets/ or data/ tree at all."""
    jar = _jar(tmp_path / "perf.jar", {"com/p/Mix": _classfile("com/p/Mix")})
    res = convert(jar, tmp_path / "out")
    assert res.outcome == codeonly.OUTCOME and res.namespace == "codemod"
    assert [r["class"] for r in res.reason_classes] == ["mixin_patch"]


def test_content_leftover_keeps_the_tree_empty_error(tmp_path):
    """A blockstate nobody converted is a converter gap, not an explanation."""
    jar = _screen_mod(tmp_path)
    facts = codeonly.facts(jar)
    left = [Unhandled("assets/codemod/blockstates/", "unowned", "1 file(s) no converter claims yet")]
    ok, why = codeonly.decide({}, left, facts)
    assert not ok and "unowned" in why
    data = [Unhandled("data/codemod/recipe/", "unowned", "1 file(s) no converter claims yet")]
    assert not codeonly.decide({}, data, facts)[0]
    assert not codeonly.decide({"texts/en_US.lang": "x"}, [], facts)[0]


def test_own_typed_loader_data_is_a_code_leftover(tmp_path):
    root = tmp_path / "staged"
    (root / "data/codemod/neoforge/biome_modifier").mkdir(parents=True)
    (root / "data/codemod/neoforge/biome_modifier/impl.json").write_text('{"type": "codemod:impl"}')
    u = Unhandled("data/codemod/neoforge/", "unowned", "1 file(s)")
    facts = {"classes": 3, "mixins": 2}
    assert codeonly.decide({}, [u], facts, root, ["codemod"])[0]
    (root / "data/codemod/neoforge/biome_modifier/other.json").write_text('{"type": "minecraft:add_features"}')
    assert not codeonly.decide({}, [u], facts, root, ["codemod"])[0]


def test_tree_without_report_is_still_empty(tmp_path):
    report = validate_tree(tmp_path)
    assert not report.ok and report.errors[0].rule == "tree.empty"
    (tmp_path / codeonly.REPORT_NAME).write_text(json.dumps({"outcome": "explained-empty", "reason_classes": []}))
    assert validate_tree(tmp_path).errors[0].rule == "tree.empty"  # no reason, no pass


def test_stale_report_is_removed_when_a_pack_ships(tmp_path, fixtures_dir):
    out = tmp_path / "out"
    out.mkdir()
    (out / codeonly.REPORT_NAME).write_text("{}")
    res = convert(fixtures_dir / "simple_block_mod" / "input", out)
    assert res.outcome is None and not (out / codeonly.REPORT_NAME).exists()


def test_access_flags_are_read():
    cf = ClassIndex({"a/I": _classfile("a/I", access=0x0601)}).get("a/I")
    assert cf.access & 0x0200


def _prof(environment="*", **code):
    counts = {"classes": code.pop("classes", 300), "textures": code.pop("textures", 0),
              "lang": code.pop("lang", 0), "nested_jars": 0, "api_classes": 0}
    return {"counts": counts, "flags": [], "environment": environment, "mixin_configs": [],
            "mixin_classes": {"common": code.pop("mixins", 0)}, "code": code}


def test_classify_gameplay_code_is_not_a_library():
    """A code-only jar hooking block breaks (a vein miner) reads as gameplay code."""
    cls, ev = classify(_prof(gameplay_events=["BlockEvent$BreakEvent"], events=["BlockEvent$BreakEvent"]))
    assert cls == "gameplay code" and "BreakEvent" in ev[0]


def test_classify_passive_config_library():
    """GUI widgets other mods build screens from, hooking no event of their own."""
    cls, ev = classify(_prof(textures=3, lang=20, screens=2, widgets=40))
    assert cls == "library" and ev[0].startswith("passive")
    assert classify(_prof(textures=3, lang=20, screens=2, events=["ScreenEvent$Opening"]))[0] == "UI/info"


def test_classify_client_side_screens_are_ui():
    assert classify(_prof("client", lang=10, screens=4, render=6, events=["x"]))[0] == "UI/info"
    assert classify(_prof("client", lang=10, screens=4, render=80, events=["x"]))[0] == "client-only"
    assert classify(_prof("client", lang=10, render=80, events=["x"]))[0] == "client-only"


def test_plain_code_is_reported_as_java_code():
    assert [r["class"] for r in codeonly.reason_classes({"classes": 4})] == ["java_code"]
    assert codeonly.reason_classes({"classes": 0}) == []


def test_board_counts_explained_empty_and_rolls_up_its_reasons():
    from portkit import gauntlet

    shard = {"schema": 1, "kind": "gap-shard", "manifest": "m", "shard": "1/1", "generated": "2026-10-16T00:00:00+00:00",
             "mods": {
                 "perf": {"status": "ok", "files": 0, "residue": 3, "coverage": 0.0, "valid": True, "errors": 0,
                          "outcome": "explained-empty", "mct": {"skipped": "explained-empty: no pack"},
                          "reason_classes": [{"class": "mixin_patch", "evidence": ["2 mixin(s)"]}],
                          "reasons": {"java_code: x": {"kind": "java_code", "reason": "x", "entries": 1, "files": 2},
                                      "code_only: y": {"kind": "code_only", "reason": "y", "entries": 1, "files": 1}},
                          "profile": {"class": "performance/mixin-only", "evidence": []}},
                 "gap": {"status": "ok", "files": 0, "residue": 1, "coverage": 0.0, "valid": False, "errors": 1,
                         "reasons": {}, "profile": {"class": "UI/info", "evidence": []}}}}
    b = gauntlet.board([shard])
    assert b["done"] == 1 and b["explained_empty"] == 1
    assert b["explained_empty_rollup"] == [{"reason_class": "mixin_patch", "mods": 1, "mod_names": ["perf"]}]
    md = gauntlet.render_markdown(b)
    assert "1 of them explained-empty" in md and "## Why nothing converts" in md
    assert "| explained-empty | no pack | yes |" in md
    assert gauntlet.baseline_of(b)["mods"]["perf"]["outcome"] == "explained-empty"
