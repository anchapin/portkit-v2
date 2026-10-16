"""Explained-empty: a mod with nothing Bedrock can hold, said so with reasons (#279).

About half of the top-50 gauntlet (#277) are code-only: performance patches,
client rendering, GUI and config screens, keybinds, networking, libraries.
The converter writes nothing for them, which used to look like a failure (an
empty tree the validator rejects as ``tree.empty``) with a pile of lang and
texture leftovers nobody explained.

This module makes "nothing convertible" a first-class outcome, decided from
the jar's own facts and never from its name:

* :func:`facts` reads the jar (or directory): mixin configs, the classes'
  superclasses and constant-pool references (in Mojang names, through the
  #235 remapper when a table is cached), resource formats a client renderer
  reads (shaders, OptiFine CTM/CEM/random-entity paths, ``.jem``/``.jpm``
  models), built-in resource packs and nested jars.
* :func:`reason_classes` turns them into named reason classes
  (:data:`REASONS`), each with its evidence and why Bedrock can't carry it.
* :func:`decide` says whether a conversion is explained-empty: it shipped no
  file, every residue entry is of an explained kind or a leftover a
  non-shipping mod's code uses (lang, and assets no content file names), and
  at least one reason class holds. The leftovers are re-filed as
  ``code_only`` residue (an explained kind, ``agent.residue.SKIP_KINDS``).
* :func:`write_report` writes ``explained-empty.json`` where the packs would
  have gone; :func:`portkit.validate.validate_tree` accepts a tree that holds
  that report and no packs as explained-empty rather than ``tree.empty``.

No pack is written for an explained-empty mod (#279 pick 1): a pack with no
blocks, items or entities would hold only text no Bedrock screen shows.
"""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .model import Unhandled

OUTCOME = "explained-empty"
REPORT_NAME = "explained-empty.json"
SCHEMA = 1
KIND = "code_only"

# A class is scanned for references only up to this many classes, so a huge
# jar can't stall a conversion; the facts then say how many were read.
_MAX_SCAN = 20_000

# Mojang names (a Fabric/Forge jar reads in them once the #235 table is
# attached). Prefixes match a package, full names a class.
_SCREEN = "net/minecraft/client/gui/screens/Screen"
_WIDGET_PREFIX = "net/minecraft/client/gui/components/"
# The world/entity renderer. blaze3d (RenderSystem, vertex buffers) is counted
# apart: GUI code draws through it too.
_RENDERER_PREFIX = "net/minecraft/client/renderer/"
_BLAZE3D_PREFIX = "com/mojang/blaze3d/"
_KEY_MAPPING = "net/minecraft/client/KeyMapping"
_KEY_REGISTRATION = ("net/neoforged/neoforge/client/event/RegisterKeyMappingsEvent",
                     "net/minecraftforge/client/event/RegisterKeyMappingsEvent",
                     "net/fabricmc/fabric/api/client/keybinding/v1/KeyBindingHelper")
_PAYLOAD = "net/minecraft/network/protocol/common/custom/CustomPacketPayload"
_NETWORK_PREFIXES = ("net/neoforged/neoforge/network/", "net/minecraftforge/network/",
                     "net/fabricmc/fabric/api/networking/", "net/fabricmc/fabric/api/client/networking/")
_CONFIG_SCREEN = ("net/neoforged/neoforge/client/gui/IConfigScreenFactory",
                  "net/minecraftforge/client/ConfigScreenHandler",
                  "net/minecraftforge/client/ConfigScreenHandler$ConfigScreenFactory")
_HUD = ("net/neoforged/neoforge/client/event/RenderGuiEvent", "net/neoforged/neoforge/client/event/RenderGuiLayerEvent",
        "net/neoforged/neoforge/client/event/RegisterGuiLayersEvent",
        "net/neoforged/neoforge/client/event/CustomizeGuiOverlayEvent",
        "net/minecraftforge/client/event/RenderGuiOverlayEvent", "net/minecraftforge/client/event/RenderGuiEvent",
        "net/minecraftforge/client/event/CustomizeGuiOverlayEvent",
        "net/fabricmc/fabric/api/client/rendering/v1/HudRenderCallback",
        "net/minecraft/client/gui/Gui")
_COMMAND_PREFIXES = ("com/mojang/brigadier/", "net/minecraft/commands/Commands")
# Loader events that hook the game world itself: blocks broken or placed,
# players and living entities acting. A mod listening to these changes play
# from code (a vein miner, a stack merger), not from data.
_GAMEPLAY_EVENT = re.compile(
    r"^net/(neoforged/neoforge|minecraftforge)/event/(level/BlockEvent|entity/player/|entity/living/|"
    r"entity/EntityJoinLevelEvent|entity/item/)"
    r"|^net/fabricmc/fabric/api/event/(player|entity|world)/")
# Any loader event outside registration and reload: a mod listening to none
# runs nothing of its own (a library other mods call).
_ANY_EVENT = re.compile(r"^net/(neoforged/neoforge|minecraftforge)/(client/)?event/|^net/fabricmc/fabric/api/.+Events?$|"
                        r"^net/fabricmc/fabric/api/.+Callback$")
_PASSIVE_EVENT = re.compile(r"Register|Reload|Setup|Lifecycle|Construct|ModConfig")

# Resource formats a client renderer reads from resource packs. Bedrock's
# renderer is fixed: no shader packs, no connected textures, no per-entity
# random or emissive textures, no Java entity model overrides.
_SHADER_FILE = re.compile(r"(^|/)shaders/.+|\.(glsl|vsh|fsh|csh|gsh)$")
_FORMAT_MARKERS = {
    "OptiFine CTM (connected textures)": ("optifine/ctm", "ctm.properties", "method=ctm"),
    "OptiFine CEM/EMF entity models (.jem/.jpm)": (".jem", ".jpm", "optifine/cem"),
    "OptiFine random/emissive entity textures (ETF)": ("optifine/random", "optifine/mob", "_e.png", "emissive.properties"),
    "shader packs": ("shaders.properties", "shaderpacks", ".fsh", ".vsh"),
}


@dataclass(frozen=True)
class Reason:
    label: str
    bedrock: str


# The reason classes, in report order. ``bedrock`` is why an add-on can't
# carry what the class names.
REASONS: dict[str, Reason] = {
    "mixin_patch": Reason(
        "performance / mixin patches",
        "the mod rewrites Minecraft's own Java code at load time (Mixin); a Bedrock add-on can't patch "
        "the game engine"),
    "client_rendering": Reason(
        "client rendering",
        "the mod changes how the Java client draws the world (render pipeline, shaders, resource formats "
        "such as CTM or entity model/texture overrides); Bedrock's renderer is fixed and add-ons can't "
        "replace it"),
    "gui_screen": Reason(
        "GUI screens",
        "the mod draws its own Java screens and widgets; Bedrock add-ons get only the Script API's "
        "forms, which can't host a Java screen"),
    "hud_overlay": Reason(
        "HUD overlay",
        "the mod draws on the in-game HUD from Java code; Bedrock add-ons can't draw arbitrary HUD "
        "elements"),
    "config_screen": Reason(
        "config screen",
        "the mod registers an in-game config screen; Bedrock has no mod config menu"),
    "keybind": Reason(
        "keybinds",
        "the mod registers its own key bindings; Bedrock add-ons can't add controls"),
    "networking": Reason(
        "networking",
        "the mod defines its own client/server packets; Bedrock add-ons have no custom packets"),
    "commands": Reason(
        "commands",
        "the mod registers Java (Brigadier) commands implemented in code"),
    "gameplay_hooks": Reason(
        "gameplay hooks in code",
        "the mod changes play by listening to game events in Java code (blocks broken, players or "
        "entities acting); there is no deterministic mapping to the Bedrock Script API"),
    "library_api": Reason(
        "library API",
        "the mod is code other mods call (an API, event hub, language runtime or bundle of modules); "
        "it has no content of its own"),
    "nested_modules": Reason(
        "nested modules",
        "the mod's code ships in jars nested inside it, which are not unpacked"),
}


def _refs(cf) -> set[str]:
    """Classes a class file names: reference owners and class literals."""
    out: set[str] = set()
    for i, entry in enumerate(cf.pool):
        if not isinstance(entry, tuple) or not entry:
            continue
        try:
            value = cf.constant(i)
        except Exception:  # noqa: BLE001 - an odd pool entry is skipped, not fatal
            continue
        owner = getattr(value, "owner", None)
        if owner:
            out.add(owner)
        elif isinstance(value, tuple) and len(value) == 2 and value[0] == "class" and isinstance(value[1], str):
            out.add(value[1])
    return out


def _strings(cf) -> list[str]:
    out = []
    for i, entry in enumerate(cf.pool):
        if not isinstance(entry, tuple) or not entry:
            continue
        try:
            value = cf.constant(i)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(value, str):
            out.append(value)
    return out


def _supers(classes, name: str, limit: int = 12) -> list[str]:
    """The superclass chain of ``name`` as far as the jar (and the names) go."""
    chain, seen = [], set()
    cf = classes.get(name)
    while cf is not None and cf.super_name and len(chain) < limit and cf.super_name not in seen:
        chain.append(cf.super_name)
        seen.add(cf.super_name)
        cf = classes.get(cf.super_name)
    return chain


def scan_classes(classes) -> dict:
    """Code facts from a :class:`portkit.bytecode.ClassIndex` (Mojang names)."""
    names = classes.names() if classes is not None else []
    facts = {"classes": len(names), "scanned": 0, "screens": 0, "widgets": 0, "render": 0, "blaze3d": 0,
             "key_mappings": 0, "key_registration": 0, "payloads": 0, "network": 0, "config_screen": 0,
             "hud": 0, "commands": 0, "gameplay_events": [], "events": [], "event_classes": 0,
             "formats": []}
    gameplay, events, formats = set(), set(), set()
    for name in names[:_MAX_SCAN]:
        cf = classes.get(name)
        if cf is None:
            continue
        facts["scanned"] += 1
        chain = _supers(classes, name)
        if _SCREEN in chain or any(s.startswith("net/minecraft/client/gui/screens/") for s in chain):
            facts["screens"] += 1
        elif any(s.startswith(_WIDGET_PREFIX) for s in chain):
            facts["widgets"] += 1
        if _PAYLOAD in cf.interfaces:
            facts["payloads"] += 1
        simple = name.rsplit("/", 1)[-1]
        if "$" not in simple and re.search(r"Events?$", simple):
            facts["event_classes"] += 1
        refs = _refs(cf)
        if any(r.startswith(_RENDERER_PREFIX) for r in refs):
            facts["render"] += 1
        if any(r.startswith(_BLAZE3D_PREFIX) for r in refs):
            facts["blaze3d"] += 1
        if _KEY_MAPPING in refs:
            facts["key_mappings"] += 1
        if refs & set(_KEY_REGISTRATION):
            facts["key_registration"] += 1
        if any(r.startswith(_NETWORK_PREFIXES) for r in refs):
            facts["network"] += 1
        if refs & set(_CONFIG_SCREEN):
            facts["config_screen"] += 1
        if any(r.split("$")[0] in _HUD for r in refs):
            facts["hud"] += 1
        if any(r.startswith(_COMMAND_PREFIXES) for r in refs):
            facts["commands"] += 1
        for r in refs:
            if _GAMEPLAY_EVENT.search(r):
                gameplay.add(r.rsplit("/", 1)[-1])
            if _ANY_EVENT.search(r) and not _PASSIVE_EVENT.search(r.rsplit("/", 1)[-1]):
                events.add(r.rsplit("/", 1)[-1])
        for text in _strings(cf):
            low = text.lower()
            for fmt, markers in _FORMAT_MARKERS.items():
                if any(m in low for m in markers):
                    formats.add(fmt)
    facts["gameplay_events"] = sorted(gameplay)
    facts["events"] = sorted(events)
    facts["formats"] = sorted(formats)
    return facts


def _members(source: Path) -> list[str]:
    source = Path(source)
    if source.is_file() and zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as zf:
            return [n for n in zf.namelist() if not n.endswith("/")]
    if source.is_dir():
        return sorted(p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file())
    return []


def _jar_metadata(source: Path) -> dict:
    """Loader metadata and mixin class counts (shared with the gauntlet profile)."""
    from .gauntlet import _metadata  # the profile's reader; imported late (gauntlet imports this module)

    source = Path(source)
    if source.is_file() and zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as zf:
            return _metadata(zf, [n for n in zf.namelist() if not n.endswith("/")])
    if source.is_dir():
        import io

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for p in source.rglob("*"):
                rel = p.relative_to(source).as_posix()
                if p.is_file() and not rel.endswith(".class") and "/" not in rel.strip("/").replace(
                        "META-INF/", "", 1):
                    zf.write(p, rel)
        with zipfile.ZipFile(buf) as zf:
            return _metadata(zf, zf.namelist())
    return {}


def facts(source: Path, classes=None) -> dict:
    """Everything :func:`reason_classes` decides from, read from the jar.

    ``classes`` is the mod's :class:`portkit.bytecode.ClassIndex` when the
    caller has one (the pipeline's, already remapped); otherwise the jar's
    classes are read here and the #235 mapping table attached when cached.
    """
    from .bytecode import ClassIndex

    source = Path(source)
    members = _members(source)
    meta = _jar_metadata(source)
    if classes is None:
        classes = ClassIndex.from_source(source)
        _attach_mappings(classes, source)
    code = scan_classes(classes)
    shader_files = [n for n in members if n.startswith("assets/") and _SHADER_FILE.search(n)
                    or "/" not in n and _SHADER_FILE.search(n)]
    builtin_packs = sorted({n.split("/")[1] for n in members if n.startswith("resourcepacks/") and n.count("/") >= 2})
    path_formats = sorted({fmt for fmt, markers in _FORMAT_MARKERS.items()
                           for n in members if any(m in n.lower() for m in markers if "/" in m or m.startswith("."))})
    mixin_classes = meta.get("mixin_classes") or {}
    return {
        **code,
        "formats": sorted(set(code["formats"]) | set(path_formats)),
        "mixin_configs": len(meta.get("mixin_configs") or ()),
        "mixins": sum(mixin_classes.values()),
        "client_mixins": mixin_classes.get("client", 0),
        "shader_files": len(shader_files),
        "builtin_resource_packs": builtin_packs,
        "nested_jars": sum(1 for n in members if re.match(r"^META-INF/(jars|jarjar)/.+\.jar$", n)),
        "environment": meta.get("environment", "unknown"),
        "entrypoints": meta.get("entrypoints", []),
        "flags": meta.get("flags", []),
        "api_classes": sum(1 for n in members if n.endswith(".class") and re.search(r"(^|/)api/", n)),
        "lang_files": sum(1 for n in members if re.match(r"^assets/[^/]+/lang/", n)),
        "textures": sum(1 for n in members if re.match(r"^assets/[^/]+/textures/.+\.png$", n)),
    }


def _attach_mappings(classes, source: Path) -> None:
    from .data.mappings import attach
    from .ingest import METADATA_NAMES
    from .meta import parse

    metadata = {}
    try:
        if source.is_file() and zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as zf:
                names = set(zf.namelist())
                metadata = {n: zf.read(n) for n in METADATA_NAMES if n in names}
        elif source.is_dir():
            metadata = {n: (source / n).read_bytes() for n in METADATA_NAMES if (source / n).is_file()}
        meta = parse(metadata, "")
        attach(classes, meta.loader, meta.minecraft)
    except Exception:  # noqa: BLE001 - without a table the names read as compiled
        pass


def library_evidence(f: dict) -> list[str]:
    """Why the jar reads as code other mods call, or [] (shared with
    :func:`portkit.gauntlet.classify`)."""
    flags = set(f.get("flags") or ())
    out = []
    if "language_adapter" in flags:
        out.append("provides a language adapter")
    if "modmenu_library_badge" in flags:
        out.append("Mod Menu badge \"library\"")
    classes = f.get("classes", 0)
    if f.get("nested_jars", 0) >= 5 and classes <= 10:
        out.append(f"bundles {f['nested_jars']} nested jars, {classes} classes of its own")
    if classes and f.get("api_classes", 0) * 2 >= classes:
        out.append(f"api classes {f['api_classes']}/{classes}")
    if f.get("event_classes", 0) >= 10 and classes >= 100 and not f.get("textures"):
        # An event hub for other mods; a mod with art of its own (a voice chat,
        # a map) that also offers plugin events is not one.
        out.append(f"defines an event API ({f['event_classes']} *Event(s) classes) and ships no textures")
    mixins = f.get("mixins", 0)
    if (classes >= 50 and mixins * 20 < classes and not f.get("events") and not f.get("key_registration")
            and not f.get("gameplay_events") and not f.get("hud") and f.get("environment") != "client"):
        out.append(f"passive: {classes} classes hook no game, input, screen or render event and register "
                   "no keybind (code other mods call)")
    return out


def reason_classes(f: dict) -> list[dict]:
    """The named reason classes the facts support, each with its evidence."""
    out: dict[str, list[str]] = {}
    classes = f.get("classes", 0)
    if f.get("mixins"):
        out["mixin_patch"] = [f"{f['mixins']} mixin(s) in {f.get('mixin_configs', 0)} config(s)"
                              + (f", {f['client_mixins']} client-side" if f.get("client_mixins") else "")]
    render = []
    if f.get("render", 0) >= 10:
        render.append(f"{f['render']} class(es) call the world/entity renderer (client.renderer)")
    if f.get("shader_files"):
        render.append(f"{f['shader_files']} shader file(s)")
    for fmt in f.get("formats") or ():
        render.append(f"reads {fmt}")
    if f.get("builtin_resource_packs"):
        render.append("built-in Java resource pack(s): " + ", ".join(f["builtin_resource_packs"][:3]))
    if render:
        out["client_rendering"] = render
    if f.get("screens") or f.get("widgets", 0) >= 3:
        out["gui_screen"] = [f"{f.get('screens', 0)} screen class(es), {f.get('widgets', 0)} widget class(es)"]
    if f.get("hud"):
        out["hud_overlay"] = [f"{f['hud']} class(es) hook the HUD"]
    if f.get("config_screen") or "modmenu" in (f.get("entrypoints") or ()):
        ev = []
        if f.get("config_screen"):
            ev.append(f"{f['config_screen']} class(es) register a config screen factory")
        if "modmenu" in (f.get("entrypoints") or ()):
            ev.append("declares a modmenu entrypoint")
        out["config_screen"] = ev
    if f.get("key_registration") or f.get("key_mappings", 0) >= 2:
        out["keybind"] = [f"{f.get('key_registration', 0)} class(es) register key mappings, "
                          f"{f.get('key_mappings', 0)} use them"]
    if f.get("payloads") or f.get("network"):
        out["networking"] = [f"{f.get('payloads', 0)} custom packet payload(s), "
                             f"{f.get('network', 0)} class(es) use the loader's network API"]
    if f.get("commands", 0) >= 2:
        out["commands"] = [f"{f['commands']} class(es) use Brigadier commands"]
    if f.get("gameplay_events"):
        out["gameplay_hooks"] = ["listens to " + ", ".join(f["gameplay_events"][:4])
                                 + (" …" if len(f["gameplay_events"]) > 4 else "")]
    lib = library_evidence(f)
    if lib:
        out["library_api"] = lib
    if f.get("nested_jars"):
        out["nested_modules"] = [f"{f['nested_jars']} nested jar(s)"]
    if classes and not out:
        # Code with none of the shapes above is still code: say so rather
        # than leave the outcome unexplained.
        out["gameplay_hooks"] = [f"{classes} class(es) of Java code with no content files"]
    return [{"class": k, "label": REASONS[k].label, "evidence": out[k], "bedrock": REASONS[k].bedrock}
            for k in REASONS if k in out]


# Asset directories a Bedrock pack would carry (blockstates, item
# definitions, sounds): a leftover there is a converter gap, not an
# explanation, so it keeps the mod from being explained-empty. Every other
# assets/<ns>/ leftover of a mod that ships nothing (GUI textures, renderer
# models, shaders, fonts) is only read by the mod's code. data/ leftovers are
# never explained this way.
_CONTENT_ASSET_DIRS = frozenset({"blockstates", "items", "sounds", "sounds.json"})


def _explained_kinds() -> frozenset:
    from .agent.residue import SKIP_KINDS

    return frozenset(SKIP_KINDS)


def _leftover_dir(source: str) -> str | None:
    parts = source.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "assets":
        return parts[2]
    return None


_LOADER_DATA = frozenset({"neoforge", "forge", "fabric", "quilt"})


def _own_typed_data(root: Path | None, source: str, namespaces) -> bool:
    """A loader data folder (``data/<ns>/neoforge/...``) whose every file is a
    JSON object typed with one of the mod's own namespaces: a codec the mod's
    code registers and reads itself (Architectury-style ``"type": "<ns>:impl"``
    hooks), so with no content shipped nothing else would read it."""
    parts = source.strip("/").split("/")
    if root is None or len(parts) < 3 or parts[0] != "data" or parts[2] not in _LOADER_DATA:
        return False
    files = [p for p in (Path(root) / source.strip("/")).rglob("*") if p.is_file()]
    if not files:
        return False
    own = tuple(f"{ns}:" for ns in namespaces)
    for path in files:
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            return False
        if not isinstance(doc, dict) or not str(doc.get("type", "")).startswith(own):
            return False
    return True


def _is_code_leftover(u: Unhandled, root: Path | None = None, namespaces=()) -> bool:
    if u.kind in ("lang", "lang_code_string"):
        return True
    if u.kind != "unowned":
        return False
    if _own_typed_data(root, u.source, namespaces):
        return True
    sub = _leftover_dir(u.source)
    if sub is None:
        return False
    # Under assets/<ns>/: anything but the content folders (blockstates,
    # item definitions, sounds), which a Bedrock pack would carry.
    return sub not in _CONTENT_ASSET_DIRS


def decide(files: dict, unhandled: list[Unhandled], f: dict | None, root: Path | None = None,
           namespaces=()) -> tuple[bool, str]:
    """(explained_empty, why not). Explained-empty when the conversion shipped
    nothing, every residue entry is explained or a code leftover, and the
    jar's facts name at least one reason class."""
    if files:
        return False, "the conversion shipped files"
    explained = _explained_kinds()
    open_ = sorted({u.kind for u in unhandled if u.kind not in explained and not _is_code_leftover(u, root, namespaces)})
    if open_:
        return False, "residue of kind(s) " + ", ".join(open_) + " is not explained"
    if not f or not reason_classes(f):
        return False, "no reason class found in the jar"
    return True, ""


def explain_leftovers(unhandled: list[Unhandled], reasons: list[dict], root: Path | None = None,
                      namespaces=()) -> list[Unhandled]:
    """Re-file a non-shipping mod's lang and asset leftovers as ``code_only``
    residue (explained), one entry per source; everything else unchanged."""
    named = ", ".join(r["class"] for r in reasons) or "none"
    out: list[Unhandled] = []
    lang_keys: dict[str, int] = {}
    for u in unhandled:
        if not _is_code_leftover(u, root, namespaces):
            out.append(u)
            continue
        if u.kind in ("lang", "lang_code_string"):
            lang_keys[u.source] = lang_keys.get(u.source, 0) + 1
            continue
        sub = _leftover_dir(u.source) or "data"
        if _own_typed_data(root, u.source, namespaces):
            out.append(Unhandled(
                source=u.source, kind=KIND, count=u.count,
                reason=(f"{u.count} loader data file(s) typed with the mod's own codec, which only its Java "
                        f"code reads; the mod ships nothing Bedrock can hold (reason classes: {named})")))
            continue
        out.append(Unhandled(
            source=u.source, kind=KIND, count=u.count,
            reason=(f"{u.count} {sub} file(s) only the mod's Java code reads; the mod ships nothing Bedrock "
                    f"can hold (reason classes: {named}), so no pack would carry them")))
    for source in sorted(lang_keys):
        out.append(Unhandled(
            source=source, kind=KIND,
            reason=(f"text the mod's Java code shows ({lang_keys[source]} residue line(s) folded); the mod "
                    f"ships nothing Bedrock can hold (reason classes: {named}), so no pack would show it")))
    return out


def report(meta, reasons: list[dict], unhandled: list[Unhandled], f: dict) -> dict:
    counts: dict[str, int] = {}
    for u in unhandled:
        counts[u.kind] = counts.get(u.kind, 0) + u.count
    return {
        "schema": SCHEMA, "outcome": OUTCOME,
        "mod": {"name": getattr(meta, "name", None), "id": getattr(meta, "mod_id", None),
                "loader": getattr(meta, "loader", None)},
        "summary": ("Nothing in this mod converts to a Bedrock add-on, so no pack was written: "
                    + "; ".join(r["label"] for r in reasons) + "."),
        "reason_classes": reasons,
        "residue_files": dict(sorted(counts.items())),
        "facts": {k: f.get(k) for k in ("classes", "mixins", "mixin_configs", "screens", "widgets", "render", "blaze3d",
                                          "key_registration", "payloads", "network", "commands", "hud",
                                          "shader_files", "nested_jars", "formats", "environment")},
    }


def write_report(out_dir: Path, doc: dict) -> Path:
    path = Path(out_dir) / REPORT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def read_report(tree: Path) -> dict | None:
    """The explained-empty report in ``tree``, if it is a well-formed one."""
    path = Path(tree) / REPORT_NAME
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if (not isinstance(doc, dict) or doc.get("outcome") != OUTCOME
            or not isinstance(doc.get("reason_classes"), list) or not doc["reason_classes"]
            or any(not isinstance(r, dict) or r.get("class") not in REASONS for r in doc["reason_classes"])):
        return None
    return doc
