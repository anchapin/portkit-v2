"""The top-50 gauntlet (#277, harness #278): pin, profile, run and board.

#277 works through the 50 most popular Java mods end to end. This module is
the harness every #277 sub-issue runs on:

1. ``pin`` resolves each of the 50 (``THE_50``) to one jar by the version rule
   (``RULE_VERSIONS`` / ``LOADER_PREFERENCE``) and writes
   ``fixtures/real/gauntlet.toml`` in the corpus manifest format, so
   ``portkit.corpus`` loads and fetches it (sha512-checked, never committed).
   Modrinth first (``api.modrinth.com/v2``); a mod that is not on Modrinth is
   pinned from CurseForge's CDN (see ``pin_curseforge``), or recorded as
   ``unfetchable`` with the reason.
2. ``profile`` reads a jar's own contents (file counts by kind, mixin configs,
   entrypoints, declared dependencies) and ``classify`` puts it in one class:
   content, library, performance/mixin-only, client-only or UI/info. The
   class comes from the jar, never from the mod's description.
3. ``portkit gauntlet run`` is ``portkit gaps run`` (#234) over this manifest
   with the profile added to each mod's record: same child-process
   conversion, normalized reasons, mct counts and shard files.
4. ``board`` merges the shards with ``gaps.leaderboard`` and adds the
   gauntlet's own view: per mod class, coverage, residue by reason class,
   validate/mct status and #277's "done" flag (rule 6), plus the cross-mod
   reason-class roll-up that ranks the next general work (rule 4).
   ``render_markdown`` writes ``docs/gauntlet.md``; ``baseline`` is the
   banked reference (``fixtures/real/gauntlet-baseline.json``), kept apart
   from the 13-mod corpus so the PR gate stays fast.

Nothing here changes a conversion.
"""
from __future__ import annotations

import hashlib
import json
import re
import tomllib
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import gaps

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "fixtures" / "real" / "gauntlet.toml"
BASELINE = ROOT / "fixtures" / "real" / "gauntlet-baseline.json"
SCHEMA = 1

MODRINTH = "https://api.modrinth.com/v2"
CFWIDGET = "https://api.cfwidget.com/minecraft/mc-mods"
FORGECDN = "https://mediafilez.forgecdn.net/files"
_USER_AGENT = "anchapin/portkit-v2 gauntlet pin (github.com/anchapin/portkit-v2)"

# --- the version rule (#278 pick 1) ------------------------------------------
# The newest build for Minecraft 1.21.1, else 1.20.1, on the loader the
# converter reads best for that version. Releases are taken before betas and
# alphas across every slot, so a 1.20.1 release beats a 1.21.1 beta.
#
# Loader order, from what the converter has for each (docs/decisions.md):
#   1.21.1: NeoForge jars hold Mojang names (no remapping) and have the
#           neoforge-1.21.1 tag set; Fabric has fabric-1.21.1 tags but needs
#           the intermediary table (8-10 ambiguous ids per version); Forge
#           1.21+ has neither a pinned name table nor a tag set; Quilt last.
#   1.20.1: Forge has the forge-1.20.1 tag set and SRG (no ambiguous ids);
#           Fabric has fabric-1.20.1 tags and intermediary; NeoForge 1.20.1
#           reads as Forge (SRG) but has no tag set of its own; Quilt last.
RULE_VERSIONS = ("1.21.1", "1.20.1")
LOADER_PREFERENCE = {
    "1.21.1": ("neoforge", "fabric", "forge", "quilt"),
    "1.20.1": ("forge", "fabric", "neoforge", "quilt"),
}


@dataclass(frozen=True)
class Listed:
    """One of #277's 50, as the issue lists it."""
    rank: int
    name: str
    title: str
    modrinth: str = ""        # Modrinth slug, when the mod is hosted there
    curseforge: str = ""      # CurseForge slug, for mods only hosted there
    listed_lib: bool = False  # #277 marks it [lib]; kept to compare with the jar's class
    licence: str = ""         # CurseForge-only mods: the licence, read from the source repo
    licence_source: str = ""
    redistribution: str = ""


# The 50, in #277's order. Modrinth slugs were checked against
# api.modrinth.com/v2/project/<slug> on 2026-10-16; Twilight Forest and Chisel
# are not on Modrinth (search finds only unofficial ports and other mods).
THE_50: tuple[Listed, ...] = (
    Listed(1, "jei", "Just Enough Items (JEI)", "jei"),
    Listed(2, "sodium", "Sodium", "sodium"),
    Listed(3, "fabric_api", "Fabric API", "fabric-api", listed_lib=True),
    Listed(4, "iris", "Iris Shaders", "iris"),
    Listed(5, "entityculling", "Entity Culling", "entityculling"),
    Listed(6, "cloth_config", "Cloth Config API", "cloth-config", listed_lib=True),
    Listed(7, "ferritecore", "FerriteCore", "ferrite-core"),
    Listed(8, "modmenu", "Mod Menu", "modmenu"),
    Listed(9, "lithium", "Lithium", "lithium"),
    Listed(10, "immediatelyfast", "ImmediatelyFast", "immediatelyfast"),
    Listed(11, "yacl", "YetAnotherConfigLib (YACL)", "yacl", listed_lib=True),
    Listed(12, "fabric_language_kotlin", "Fabric Language Kotlin", "fabric-language-kotlin", listed_lib=True),
    Listed(13, "xaeros_minimap", "Xaero's Minimap", "xaeros-minimap"),
    Listed(14, "entity_texture_features", "Entity Texture Features", "entitytexturefeatures"),
    Listed(15, "architectury_api", "Architectury API", "architectury-api", listed_lib=True),
    Listed(16, "sodium_extra", "Sodium Extra", "sodium-extra"),
    Listed(17, "xaeros_world_map", "Xaero's World Map", "xaeros-world-map"),
    Listed(18, "entity_model_features", "Entity Model Features", "entity-model-features"),
    Listed(19, "veinminer", "VeinMiner", "veinminer"),
    Listed(20, "appleskin", "AppleSkin", "appleskin"),
    Listed(21, "not_enough_animations", "Not Enough Animations", "not-enough-animations"),
    Listed(22, "reeses_sodium_options", "Reese's Sodium Options", "reeses-sodium-options"),
    Listed(23, "skin_layers_3d", "3D Skin Layers", "3dskinlayers"),
    Listed(24, "modernfix", "ModernFix", "modernfix"),
    Listed(25, "continuity", "Continuity", "continuity"),
    Listed(26, "geckolib", "GeckoLib", "geckolib", listed_lib=True),
    Listed(27, "simple_voice_chat", "Simple Voice Chat", "simple-voice-chat"),
    Listed(28, "placeholder_api", "Text Placeholder API", "placeholder-api", listed_lib=True),
    Listed(29, "jade", "Jade", "jade"),
    Listed(30, "waystones", "Waystones", "waystones"),
    Listed(31, "journeymap", "JourneyMap", "journeymap"),
    Listed(32, "quark", "Quark", "quark"),
    Listed(33, "ae2", "Applied Energistics 2", "ae2"),
    Listed(34, "twilight_forest", "The Twilight Forest", curseforge="the-twilight-forest",
           licence="LGPL-2.1-only (code); CC-BY-NC-SA-4.0 (assets)",
           licence_source="https://github.com/TeamTwilight/twilightforest (LICENSE, ASSET_LICENSE)",
           redistribution=("licences allow copying with attribution (assets non-commercial, share-alike); "
                           "CurseForge's third-party distribution flag needs its API key and was not read; "
                           "jar measured and discarded, cached only in this repo's Actions cache")),
    Listed(35, "tinkers_construct", "Tinkers' Construct", "tinkers-construct"),
    Listed(36, "biomes_o_plenty", "Biomes O' Plenty", "biomes-o-plenty"),
    Listed(37, "immersive_engineering", "Immersive Engineering", "immersiveengineering"),
    Listed(38, "botania", "Botania", "botania"),
    Listed(39, "storage_drawers", "Storage Drawers", "storagedrawers"),
    Listed(40, "iron_chests", "Iron Chests", "iron-chests"),
    Listed(41, "mouse_tweaks", "Mouse Tweaks", "mouse-tweaks"),
    Listed(42, "controlling", "Controlling", "controlling"),
    Listed(43, "natures_compass", "Nature's Compass", "natures-compass"),
    Listed(44, "clumps", "Clumps", "clumps"),
    Listed(45, "enchantment_descriptions", "Enchantment Descriptions", "enchantment-descriptions"),
    Listed(46, "just_enough_resources", "Just Enough Resources (JER)", "just-enough-resources-jer"),
    Listed(47, "better_advancements", "Better Advancements", "better-advancements"),
    Listed(48, "comforts", "Comforts", "comforts"),
    Listed(49, "cooking_for_blockheads", "Cooking for Blockheads", "cooking-for-blockheads"),
    Listed(50, "chisel", "Chisel", curseforge="chisel",
           licence="GPL-2.0-only",
           licence_source="https://github.com/Chisel-Team/Chisel (repository licence)",
           redistribution=("GPL-2.0 allows copying; CurseForge's third-party distribution flag needs its API "
                           "key and was not read; jar measured and discarded, cached only in this repo's "
                           "Actions cache")),
)


class PinError(Exception):
    """A host answered with something the pin can't use."""


def _get_json(url: str, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise PinError(f"GET {url}: {exc}") from exc


def _rule_slots():
    for mc in RULE_VERSIONS:
        for loader in LOADER_PREFERENCE[mc]:
            yield mc, loader


def pick(builds: list[dict]) -> tuple[dict, str] | None:
    """The build the version rule picks, and the rule branch that picked it.

    ``builds`` are host-neutral: {"type": release|beta|alpha, "loaders": [...],
    "game_versions": [...], "date": iso, ...}. Newest first within a slot.
    """
    ordered = sorted(builds, key=lambda b: b.get("date") or "", reverse=True)
    for types, label in ((("release",), "release"), (("beta", "alpha"), "pre-release")):
        for mc, loader in _rule_slots():
            for b in ordered:
                if b.get("type") in types and mc in b["game_versions"] and loader in b["loaders"]:
                    return b, f"{mc} {loader} {label}"
    return None


def pick_off_rule(builds: list[dict]) -> tuple[dict, str] | None:
    """No 1.21.1 or 1.20.1 build: the newest release (else newest build) on a
    Java loader, flagged off-rule so the board says so."""
    ordered = sorted(builds, key=lambda b: b.get("date") or "", reverse=True)
    java = [b for b in ordered if set(b["loaders"]) & {"fabric", "forge", "neoforge", "quilt"}]
    for b in java:
        if b.get("type") == "release":
            return b, "off-rule: no 1.21.1 or 1.20.1 build; newest release"
    if java:
        return java[0], "off-rule: no 1.21.1 or 1.20.1 build; newest build"
    return None


def _modrinth_builds(versions: list) -> list[dict]:
    out = []
    for v in versions if isinstance(versions, list) else []:
        files = v.get("files") or []
        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not primary or not str(primary.get("filename", "")).endswith(".jar"):
            continue
        sha = (primary.get("hashes") or {}).get("sha512")
        if not sha:
            continue
        out.append({"type": v.get("version_type"), "loaders": list(v.get("loaders") or ()),
                    "game_versions": list(v.get("game_versions") or ()), "date": v.get("date_published", ""),
                    "id": v["id"], "version": v.get("version_number", ""), "url": primary["url"],
                    "sha512": sha})
    return out


def pin_modrinth(item: Listed, opener=urllib.request.urlopen) -> dict:
    project = _get_json(f"{MODRINTH}/project/{item.modrinth}", opener)
    versions = _get_json(f"{MODRINTH}/project/{project['id']}/version", opener)
    builds = _modrinth_builds(versions)
    chosen = pick(builds) or pick_off_rule(builds)
    if chosen is None:
        return _unfetchable(item, "modrinth", f"no Java-loader .jar on Modrinth project {item.modrinth}",
                            licence=(project.get("license") or {}).get("id", ""))
    build, rule = chosen
    mc, loader = _slot_of(build, rule)
    return {
        "name": item.name, "rank": item.rank, "title": item.title, "project": item.modrinth,
        "host": "modrinth", "version_id": build["id"], "version": build["version"],
        "loader": loader, "minecraft": mc, "rule": rule,
        "license": (project.get("license") or {}).get("id", "") or "unknown",
        "redistribution": "Modrinth CDN, measured and discarded, never committed (as the corpus, #21/#234)",
        "url": build["url"], "sha512": build["sha512"], "listed_lib": item.listed_lib,
        "notes": f"Modrinth {project.get('downloads', 0)} downloads ({date.today().isoformat()})",
    }


def _slot_of(build: dict, rule: str) -> tuple[str, str]:
    if not rule.startswith("off-rule"):
        mc, loader = rule.split()[:2]
        return mc, loader
    loaders = [x for x in ("neoforge", "fabric", "forge", "quilt") if x in build["loaders"]]
    games = [g for g in build["game_versions"] if re.fullmatch(r"\d+\.\d+(\.\d+)?", g)]
    return (games[-1] if games else ""), (loaders[0] if loaders else "")


def forgecdn_url(file_id: int, filename: str) -> str:
    """CurseForge's public CDN path for a file id: /files/<id // 1000>/<id % 1000>/<name>."""
    return f"{FORGECDN}/{file_id // 1000}/{file_id % 1000}/{urllib.parse.quote(filename)}"


_CF_LOADERS = {"Forge": "forge", "NeoForge": "neoforge", "Fabric": "fabric", "Quilt": "quilt"}


def _cf_builds(files: list) -> list[dict]:
    """CurseForge file ids rise with upload time, so the id orders the builds
    (newest first) without parsing cfwidget's timestamps."""
    out = []
    for f in files or []:
        name = str(f.get("name", ""))
        if not name.endswith(".jar"):
            continue
        tags = f.get("versions") or []
        out.append({"type": f.get("type"), "loaders": [_CF_LOADERS[t] for t in tags if t in _CF_LOADERS],
                    "game_versions": [t for t in tags if re.fullmatch(r"\d+\.\d+(\.\d+)?", t)],
                    "date": f"{int(f['id']):012d}", "id": str(f["id"]),
                    "version": f.get("display") or name, "filename": name})
    return out


def pin_curseforge(item: Listed, opener=urllib.request.urlopen, download=None) -> dict:
    """A CurseForge-only mod, pinned without CurseForge's API key.

    The file list comes from cfwidget (an open mirror of CurseForge's public
    project pages, ``api.cfwidget.com``), the jar from CurseForge's public CDN
    (``mediafilez.forgecdn.net``), and the sha512 from downloading it once
    here. When either is unreachable the mod is recorded as unfetchable with
    the reason rather than blocking the gauntlet.
    """
    try:
        data = _get_json(f"{CFWIDGET}/{item.curseforge}", opener)
    except PinError as exc:
        return _unfetchable(item, "curseforge", f"CurseForge file list unreachable without an API key ({exc})")
    builds = _cf_builds(data.get("files") or [])
    chosen = pick(builds) or pick_off_rule(builds)
    if chosen is None:
        return _unfetchable(item, "curseforge", "no Java-loader .jar in the CurseForge file list")
    build, rule = chosen
    mc, loader = _slot_of(build, rule)
    url = forgecdn_url(int(build["id"]), build["filename"])
    try:
        sha = (download or _sha512_of_url)(url, opener)
    except PinError as exc:
        return _unfetchable(item, "curseforge", f"CurseForge CDN refused the jar without an API key ({exc})")
    return {
        "name": item.name, "rank": item.rank, "title": item.title, "project": item.curseforge,
        "host": "curseforge", "version_id": build["id"], "version": build["version"],
        "loader": loader, "minecraft": mc, "rule": rule, "license": item.licence or "unknown",
        "redistribution": item.redistribution, "url": url, "sha512": sha, "listed_lib": item.listed_lib,
        "notes": f"CurseForge project {data.get('id')}; licence from {item.licence_source}",
    }


def _sha512_of_url(url: str, opener=urllib.request.urlopen) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    h = hashlib.sha512()
    try:
        with opener(req, timeout=300) as resp:
            while chunk := resp.read(1 << 20):
                h.update(chunk)
    except OSError as exc:
        raise PinError(f"GET {url}: {exc}") from exc
    return h.hexdigest()


def _unfetchable(item: Listed, host: str, reason: str, licence: str = "") -> dict:
    return {"name": item.name, "rank": item.rank, "title": item.title,
            "project": item.modrinth or item.curseforge, "host": host,
            "license": licence or item.licence or "unknown", "listed_lib": item.listed_lib,
            "unfetchable": reason, "redistribution": item.redistribution}


def pin(items=THE_50, opener=urllib.request.urlopen, download=None, log=print) -> list[dict]:
    entries = []
    for item in items:
        if item.modrinth:
            entry = pin_modrinth(item, opener)
        elif item.curseforge:
            entry = pin_curseforge(item, opener, download)
        else:
            entry = _unfetchable(item, "", "no host known")
        log(f"{item.rank:2} {item.name}: " + (f"unfetchable: {entry['unfetchable']}" if entry.get("unfetchable")
                                              else f"{entry['minecraft']} {entry['loader']} {entry['version']} ({entry['rule']})"))
        entries.append(entry)
    return entries


_KEYS = ("name", "rank", "title", "project", "host", "version_id", "version", "loader", "minecraft",
         "rule", "license", "redistribution", "url", "sha512", "listed_lib", "unfetchable", "notes")


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def render_manifest(entries: list[dict], today: str) -> str:
    head = [
        "# The top-50 gauntlet (#277, harness #278): #277's 50 mods, one pinned jar each.",
        "# Corpus manifest format (fixtures/real/mods.toml); jars are downloaded and",
        "# sha512-checked, measured and discarded, never committed. Generated, not hand-edited:",
        "#   portkit gauntlet pin",
        f"# Pinned {today}. Version rule (#278 pick 1): the newest build for Minecraft 1.21.1,",
        "# else 1.20.1, releases before pre-releases, on the loader the converter reads best",
        "# (1.21.1: neoforge, fabric, forge, quilt; 1.20.1: forge, fabric, neoforge, quilt).",
        "# `rule` says which branch picked the build; off-rule means neither version exists.",
        "# Modrinth first; CurseForge-only mods via cfwidget + CurseForge's public CDN",
        "# (#278 pick 2). `unfetchable` marks a jar that can't be fetched, with the reason.",
        "",
    ]
    body = []
    for e in entries:
        body.append("[[mod]]")
        for key in _KEYS:
            if key in e and e[key] not in ("", None):
                body.append(f"{key} = {_toml_value(e[key])}")
        body.append("")
    return "\n".join(head + body)


# --- profiling a jar ---------------------------------------------------------

_PATTERNS = {
    "blockstates": re.compile(r"^assets/[^/]+/blockstates/.+\.json$"),
    "block_models": re.compile(r"^assets/[^/]+/models/block/.+\.json$"),
    "item_models": re.compile(r"^assets/[^/]+/models/item/.+\.json$"),
    "item_definitions": re.compile(r"^assets/[^/]+/items/.+\.json$"),
    "textures": re.compile(r"^assets/[^/]+/textures/.+\.png$"),
    "gui_textures": re.compile(r"^assets/[^/]+/textures/gui/.+\.png$"),
    "lang": re.compile(r"^assets/[^/]+/lang/[^/]+\.(json|lang)$"),
    "sounds": re.compile(r"^assets/[^/]+/(sounds\.json|sounds/.+\.ogg)$"),
    "shaders": re.compile(r"^assets/[^/]+/shaders/.+|.+\.(glsl|vsh|fsh)$"),
    "recipes": re.compile(r"^data/[^/]+/recipes?/.+\.json$"),
    "loot_tables": re.compile(r"^data/[^/]+/loot_tables?/.+\.json$"),
    "advancements": re.compile(r"^data/[^/]+/advancements?/.+\.json$"),
    "tags": re.compile(r"^data/[^/]+/tags/.+\.json$"),
    "worldgen": re.compile(r"^data/[^/]+/(worldgen|dimension|dimension_type)/.+\.json$"),
    "structures": re.compile(r"^data/[^/]+/structures?/.+\.nbt$"),
    "classes": re.compile(r".+\.class$"),
    "nested_jars": re.compile(r"^META-INF/(jars|jarjar)/.+\.jar$"),
}
_ASSETS = re.compile(r"^assets/[^/]+/.+[^/]$")
_DATA = re.compile(r"^data/[^/]+/.+[^/]$")
_MIXIN_FILE = re.compile(r"^[^/]*mixins?[^/]*\.json$|^[^/]+\.mixins?\.json$", re.I)
_API_CLASS = re.compile(r"(^|/)api/.+\.class$")
_CONTENT_KEYS = ("blockstates", "item_definitions", "recipes", "loot_tables", "worldgen", "structures")


def _read_json(zf: zipfile.ZipFile, name: str):
    try:
        return json.loads(zf.read(name).decode("utf-8", "replace"))
    except (KeyError, ValueError):
        return None


def _read_toml(zf: zipfile.ZipFile, name: str):
    try:
        return tomllib.loads(zf.read(name).decode("utf-8", "replace"))
    except (KeyError, ValueError, tomllib.TOMLDecodeError):
        return None


def _manifest_attr(zf: zipfile.ZipFile, key: str) -> list[str]:
    try:
        text = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except KeyError:
        return []
    text = re.sub(r"\r?\n ", "", text)  # continuation lines
    for line in text.splitlines():
        if line.startswith(key + ":"):
            return [v.strip() for v in line.split(":", 1)[1].split(",") if v.strip()]
    return []


def profile(jar: Path | str) -> dict:
    """What the jar holds, read from its own files (no description, no host)."""
    with zipfile.ZipFile(jar) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        counts = {k: sum(1 for n in names if p.match(n)) for k, p in _PATTERNS.items()}
        counts["assets"] = sum(1 for n in names if _ASSETS.match(n))
        counts["data"] = sum(1 for n in names if _DATA.match(n))
        counts["api_classes"] = sum(1 for n in names if _API_CLASS.search(n))
        namespaces = sorted({n.split("/")[1] for n in names if _ASSETS.match(n) or _DATA.match(n)})
        meta = _metadata(zf, names)
    return {"counts": counts, "namespaces": namespaces, **meta}


def _metadata(zf: zipfile.ZipFile, names: list[str]) -> dict:
    loaders, mod_ids, deps, entrypoints, mixins, flags = [], [], set(), set(), set(), set()
    environment = ""
    fabric = _read_json(zf, "fabric.mod.json") if "fabric.mod.json" in names else None
    if isinstance(fabric, dict):
        loaders.append("fabric")
        mod_ids.append(str(fabric.get("id", "")))
        environment = str(fabric.get("environment", "") or "*")
        entrypoints |= set((fabric.get("entrypoints") or {}).keys())
        for m in fabric.get("mixins") or []:
            mixins.add(m if isinstance(m, str) else str(m.get("config", "")))
        for key in ("depends", "recommends"):
            deps |= {d for d in (fabric.get(key) or {}) if d not in ("minecraft", "java", "fabricloader")}
        if fabric.get("languageAdapters"):
            flags.add("language_adapter")
        badges = (((fabric.get("custom") or {}).get("modmenu") or {}).get("badges") or [])
        if "library" in badges:
            flags.add("modmenu_library_badge")
        if (fabric.get("custom") or {}).get("fabric-api:module-lifecycle") or fabric.get("jars"):
            if len(fabric.get("jars") or []) >= 5:
                flags.add("bundles_modules")
    quilt = _read_json(zf, "quilt.mod.json") if "quilt.mod.json" in names else None
    if isinstance(quilt, dict):
        loaders.append("quilt")
    for toml_name, loader in (("META-INF/neoforge.mods.toml", "neoforge"), ("META-INF/mods.toml", "forge")):
        if toml_name not in names:
            continue
        data = _read_toml(zf, toml_name)
        if not isinstance(data, dict):
            continue
        loaders.append(loader)
        for mod in data.get("mods") or []:
            mod_ids.append(str(mod.get("modId", "")))
            if str(mod.get("displayTest", "")).upper() == "IGNORE_ALL_VERSION":
                flags.add("display_test_ignore_all")
        if data.get("clientSideOnly") is True:
            environment = "client"
        for m in data.get("mixins") or []:
            mixins.add(str(m.get("config", "")))
        for _, entries in (data.get("dependencies") or {}).items():
            for d in entries or []:
                dep = str(d.get("modId", ""))
                required = d.get("mandatory", None) is True or str(d.get("type", "")).lower() == "required"
                if dep and dep not in ("minecraft", "forge", "neoforge", "java") and required:
                    deps.add(dep)
                if dep == "minecraft" and str(d.get("side", "")).upper() == "CLIENT" and not environment:
                    environment = "client"
        if loader == "forge" and not environment:
            environment = "*"
        if loader == "neoforge" and not environment:
            environment = "*"
    mixins |= set(_manifest_attr(zf, "MixinConfigs"))
    mixins |= {n for n in names if "/" not in n and _MIXIN_FILE.match(n)}
    mixins.discard("")
    mixin_classes = {"common": 0, "client": 0, "server": 0}
    for cfg in sorted(mixins):
        data = _read_json(zf, cfg) if cfg in names else None
        if isinstance(data, dict):
            mixin_classes["common"] += len(data.get("mixins") or [])
            mixin_classes["client"] += len(data.get("client") or [])
            mixin_classes["server"] += len(data.get("server") or [])
    if not loaders and _manifest_attr(zf, "FMLModType"):
        loaders.append("forge")
    return {"loaders": loaders, "mod_ids": [m for m in mod_ids if m], "environment": environment or "unknown",
            "entrypoints": sorted(entrypoints), "mixin_configs": sorted(mixins),
            "mixin_classes": mixin_classes, "dependencies": sorted(deps), "flags": sorted(flags)}


CLASSES = ("content", "library", "performance/mixin-only", "client-only", "UI/info")


def classify(prof: dict) -> tuple[str, list[str]]:
    """(class, evidence). First rule that holds, in this order:

    content     the jar ships game content Bedrock can hold: blockstates, item
                definitions, recipes, loot tables, worldgen or structures.
    library     the jar says it is one: a language adapter, Mod Menu's
                "library" badge, it bundles 5+ nested module jars, or most of
                its classes sit in an ``api`` package.
    performance/mixin-only
                mixin configs and no assets beyond lang, icons and config-GUI
                textures (at most 8 textures, no sounds, no shaders).
    client-only the jar declares it runs on the client only (Fabric
                environment "client", NeoForge clientSideOnly, or a minecraft
                dependency on side CLIENT).
    UI/info     everything else: screens, overlays, tooltips, keybinds.
    """
    c, flags = prof["counts"], set(prof.get("flags") or ())
    content = [f"{k} {c[k]}" for k in _CONTENT_KEYS if c.get(k)]
    if content:
        return "content", content
    lib = sorted(flags & {"language_adapter", "modmenu_library_badge", "bundles_modules"})
    if c.get("classes") and c.get("api_classes", 0) * 2 >= c["classes"]:
        lib.append(f"api classes {c['api_classes']}/{c['classes']}")
    if lib:
        return "library", lib
    mixin_total = sum((prof.get("mixin_classes") or {}).values())
    if (prof.get("mixin_configs") and c.get("textures", 0) <= 8 and not c.get("sounds")
            and not c.get("shaders") and not c.get("gui_textures", 0) > 8):
        return "performance/mixin-only", [f"{len(prof['mixin_configs'])} mixin config(s), "
                                          f"{mixin_total} mixin(s)", f"textures {c.get('textures', 0)}"]
    if prof.get("environment") == "client":
        return "client-only", ["declared client-only"]
    return "UI/info", [f"textures {c.get('textures', 0)} (gui {c.get('gui_textures', 0)})",
                       f"lang {c.get('lang', 0)}", f"environment {prof.get('environment')}"]


def profile_and_classify(jar: Path | str) -> dict:
    prof = profile(jar)
    cls, evidence = classify(prof)
    return {**prof, "class": cls, "evidence": evidence}


# --- the board ---------------------------------------------------------------

def reason_class(key: str, slot: dict) -> str:
    """The coarse class of a leaderboard reason: its residue kind, plus the
    directory shape for files no converter claims (#277 rule 4)."""
    kind = slot.get("kind") or key.split(":", 1)[0]
    m = re.search(r"\[([^\]]+)\]$", key)
    if kind in gaps._SOURCE_KEYED and m:
        parts = m.group(1).strip("/").split("/")
        return f"{kind} [{'/'.join(parts[:3])}/]"
    return kind


def _explained_kinds() -> frozenset:
    from .agent.residue import SKIP_KINDS

    return frozenset(SKIP_KINDS)


def _record_classes(record: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, slot in (record.get("reasons") or {}).items():
        rc = reason_class(key, slot)
        agg = out.setdefault(rc, {"entries": 0, "files": 0, "kind": slot.get("kind")})
        agg["entries"] += slot.get("entries", 0)
        agg["files"] += slot.get("files", 0)
    return out


def done(record: dict, explained=None) -> tuple[bool, str]:
    """#277 rule 6: converted, validator-clean, and every residue entry is of a
    kind with a documented reason the converter can't do better (the residue
    agent's SKIP_KINDS)."""
    explained = _explained_kinds() if explained is None else explained
    status = record.get("status")
    if status != "ok":
        return False, status or "?"
    if record.get("errors"):
        return False, f"{record['errors']} validator error(s)"
    open_kinds = sorted({slot.get("kind") for slot in (record.get("reasons") or {}).values()} - set(explained))
    if open_kinds:
        return False, "unexplained: " + ", ".join(open_kinds[:4]) + (" …" if len(open_kinds) > 4 else "")
    return True, "validator clean, residue explained"


def board(shards: list[dict], previous: dict | None = None, baseline: dict | None = None,
          manifest: list | None = None) -> dict:
    """The leaderboard (gaps.leaderboard) plus the gauntlet view."""
    prev_lb = (previous or {}).get("leaderboard") if previous else None
    lb = gaps.leaderboard(shards, prev_lb if previous is not None else None)
    records = {}
    for doc in shards:
        records.update(doc.get("mods", {}))
    explained = _explained_kinds()
    ranks = {m.name: getattr(m, "rank", 0) for m in (manifest or [])}
    mods, classes, rollup = [], Counter(), {}
    base_mods = (baseline or {}).get("mods", {})
    for name, rec in records.items():
        prof = rec.get("profile") or {}
        cls = prof.get("class") or ("unfetched" if rec.get("status") in ("fetch_failed", "unfetchable") else "?")
        classes[cls] += 1
        per_class = _record_classes(rec)
        is_done, why = done(rec, explained)
        row = {"name": name, "rank": rec.get("rank") or ranks.get(name, 0), "title": rec.get("title"),
               "class": cls, "evidence": prof.get("evidence", []), "status": rec.get("status"),
               "detail": rec.get("detail"), "loader": rec.get("loader"), "minecraft": rec.get("minecraft"),
               "license": rec.get("license"), "coverage": rec.get("coverage"), "files": rec.get("files"),
               "residue": rec.get("residue"), "errors": rec.get("errors"), "valid": rec.get("valid"),
               "mct": rec.get("mct"), "seconds": rec.get("seconds"), "done": is_done, "done_why": why,
               "reason_classes": dict(sorted(per_class.items(), key=lambda kv: (-kv[1]["files"], kv[0]))),
               "counts": prof.get("counts", {}), "listed_lib": rec.get("listed_lib", False)}
        base = base_mods.get(name)
        if base is not None and row["coverage"] is not None and base.get("coverage") is not None:
            row["coverage_vs_baseline"] = round(row["coverage"] - base["coverage"], 2)
        mods.append(row)
        for rc, agg in per_class.items():
            r = rollup.setdefault(rc, {"reason_class": rc, "kind": agg["kind"], "mods": 0, "entries": 0,
                                       "files": 0, "mod_names": [], "explained": agg["kind"] in explained})
            r["mods"] += 1
            r["entries"] += agg["entries"]
            r["files"] += agg["files"]
            r["mod_names"].append((agg["files"], name))
    ranked = sorted(rollup.values(), key=lambda r: (-r["mods"], -r["files"], r["reason_class"]))
    prev_roll = {r["reason_class"]: r for r in (previous or {}).get("rollup", [])}
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
        r["mod_names"] = [n for _, n in sorted(r["mod_names"], key=lambda t: (-t[0], t[1]))]
        if previous is not None:
            old = prev_roll.get(r["reason_class"])
            r["trend"] = {"new": True} if old is None else {"mods": r["mods"] - old["mods"],
                                                            "files": r["files"] - old["files"]}
    mods.sort(key=lambda m: (m["rank"] or 999, m["name"]))
    ok = [m for m in mods if m["status"] == "ok" and m["coverage"] is not None]
    return {
        "schema": SCHEMA, "kind": "gauntlet-board", "generated": lb["generated"],
        "manifest": lb["manifest"], "mods_total": len(mods), "statuses": lb["statuses"],
        "classes": {k: classes[k] for k in (*CLASSES, *sorted(set(classes) - set(CLASSES))) if classes.get(k)},
        "done": sum(1 for m in mods if m["done"]),
        "mean_coverage": round(sum(m["coverage"] for m in ok) / len(ok), 2) if ok else None,
        "rollup": ranked, "mods": mods, "leaderboard": lb,
        "baseline_generated": (baseline or {}).get("generated"),
    }


def baseline_of(b: dict) -> dict:
    """The banked reference: per mod its class and numbers."""
    return {"schema": SCHEMA, "kind": "gauntlet-baseline", "generated": b["generated"],
            "manifest": b["manifest"],
            "mods": {m["name"]: {"class": m["class"], "status": m["status"], "coverage": m["coverage"],
                                 "files": m["files"], "residue": m["residue"], "errors": m["errors"],
                                 "done": m["done"]} for m in b["mods"]}}


def _cell(text) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def _mct(m) -> str:
    mct = m.get("mct")
    if not isinstance(mct, dict):
        return ""
    if "failed" in mct:
        return "failed"
    return f"{mct.get('error', 0)}/{mct.get('warning', 0)}"


def _validate(m) -> str:
    if m["status"] != "ok":
        return ""
    return "clean" if not m.get("errors") else f"{m['errors']} error(s)"


def render_markdown(b: dict, top: int = 25) -> str:
    lines = ["# Top-50 gauntlet board", "",
             "Generated by `portkit gauntlet board` (#278) from the shards of the gap-leaderboard "
             "workflow run on `fixtures/real/gauntlet.toml`. Do not edit by hand; see "
             "[gap-leaderboard.md](gap-leaderboard.md#the-top-50-gauntlet) for how it is run.", ""]
    st = ", ".join(f"{k} {v}" for k, v in b["statuses"].items())
    cls = ", ".join(f"{k} {v}" for k, v in b["classes"].items())
    lines += [f"Generated {b['generated']}: {b['mods_total']} mods ({st}).",
              f"Classes, read from each jar's contents: {cls}.",
              f"Done under #277 rule 6 (converted, validator clean, every residue explained): {b['done']} of {b['mods_total']}.",
              "Mean coverage of converted mods: " + (f"{b['mean_coverage']}%." if b["mean_coverage"] is not None else "n/a."),
              ""]
    if b.get("baseline_generated"):
        lines += [f"Coverage deltas are against the banked baseline of {b['baseline_generated']} "
                  "(`fixtures/real/gauntlet-baseline.json`).", ""]
    lines += ["## Cross-mod reason classes (#277 rule 4)", "",
              "A reason class is a residue kind; files no converter claims (`unowned`) are split by "
              "directory. Ranked by mods, then source files. **explained** kinds are ones the residue "
              "agent skips with a documented reason (bytecode, entities, machines, ...); the rest are "
              "candidates for general converter work.", "",
              "| # | reason class | mods | files | entries | explained | mods it covers most |",
              "|---:|---|---:|---:|---:|---|---|"]
    for r in b["rollup"][:top]:
        lines.append(f"| {r['rank']} | {_cell(r['reason_class'])} | {r['mods']} | {r['files']} | {r['entries']} "
                     f"| {'yes' if r['explained'] else ''} | {_cell(', '.join(r['mod_names'][:5]))} |")
    work = [r for r in b["rollup"] if not r["explained"]][:10]
    lines += ["", "### Next general work, by mods blocked", ""]
    for i, r in enumerate(work, 1):
        lines.append(f"{i}. `{r['reason_class']}`: {r['mods']} mods, {r['files']} files "
                     f"(most in {', '.join(r['mod_names'][:3])})")
    lines += ["", "## Mods", "",
              "Coverage is the share of the jar's source files the converter wrote output for. "
              "mct is Mojang's validator, errors/warnings, report-only.", "",
              "| # | mod | class | loader / MC | status | coverage | files | residue | top reason classes "
              "| validate | mct | done |",
              "|---:|---|---|---|---|---:|---:|---:|---|---|---|---|"]
    for m in b["mods"]:
        cov = "" if m["coverage"] is None else f"{m['coverage']:.1f}%"
        if m.get("coverage_vs_baseline"):
            cov += f" ({m['coverage_vs_baseline']:+.1f})"
        status = m["status"] if m["status"] == "ok" else f"{m['status']}: {_cell(m.get('detail') or '')[:90]}"
        top3 = ", ".join(f"{k} {v['files']}" for k, v in list(m["reason_classes"].items())[:3])
        lines.append(f"| {m['rank']} | {_cell(m.get('title') or m['name'])} | {m['class']} "
                     f"| {m.get('loader') or ''} {m.get('minecraft') or ''} | {status} | {cov} "
                     f"| {m['files'] if m['files'] is not None else ''} | {m['residue'] if m['residue'] is not None else ''} "
                     f"| {_cell(top3)} | {_validate(m)} | {_mct(m)} | {'yes' if m['done'] else _cell(m['done_why'])} |")
    lines += ["", "## Class evidence", "",
              "Why each jar got its class (first rule that holds: content, library, "
              "performance/mixin-only, client-only, UI/info; `portkit.gauntlet.classify`).", "",
              "| mod | class | evidence | #277 [lib] |", "|---|---|---|---|"]
    for m in b["mods"]:
        lines.append(f"| {_cell(m.get('title') or m['name'])} | {m['class']} | {_cell('; '.join(m['evidence']))} "
                     f"| {'yes' if m.get('listed_lib') else ''} |")
    lines += ["", "## Top normalized reasons", "",
              "The gap leaderboard's finer view (#234) over the same 50.", ""]
    md = gaps.render_markdown(b["leaderboard"], top=top)
    section = md.split("## Top", 1)[1].split("## Mods", 1)[0] if "## Top" in md else ""
    lines += ["#### Top" + section.rstrip(), ""]
    return "\n".join(lines) + "\n"
