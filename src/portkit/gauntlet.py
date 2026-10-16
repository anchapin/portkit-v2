"""The top-50 gauntlet (#277, harness #278): pin, profile, run and board.

#277 works through the 50 most popular Java mods end to end. This module is
the harness every #277 sub-issue runs on:

1. ``pin`` resolves each of the 50 (``THE_50``) to one jar by the version rule
   (``RULE_VERSIONS`` / ``LOADER_PREFERENCE``) and writes
   ``fixtures/real/gauntlet.toml`` in the corpus manifest format, so
   ``portkit.corpus`` loads and fetches it (sha512-checked, never committed).
   Modrinth first (``api.modrinth.com/v2``). A mod that is only on CurseForge
   is recorded ``unfetchable`` with its pinned file id and sha512 kept as
   metadata (#278 pick 2): it is fetched only through CurseForge's official
   API with a key, and only when its author allows third-party distribution
   (see ``gate_curseforge``).
2. ``profile`` reads a jar's own contents (file counts by kind, mixin configs,
   entrypoints, declared dependencies) and ``classify`` puts it in one class:
   content, library, client-only, performance/mixin-only or UI/info. The
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

import dataclasses
import hashlib
import json
import os
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
# CurseForge (#278 pick 2, Alex 2026-10-16): only through the official API
# (``api.curseforge.com/v1`` with the ``x-api-key`` header), only with a key
# (``CURSEFORGE_API_KEY``), and only for a mod whose ``allowModDistribution``
# is true. Overwolf treats downloading from CurseForge's CDN outside the API
# as scraping, so nothing here builds a CDN url itself; the jar url is the
# ``downloadUrl`` the API hands out. CurseForge jars are fetched fresh each
# run into a temporary directory, never into the (Actions-cached) corpus cache.
CURSEFORGE_API = "https://api.curseforge.com/v1"
CURSEFORGE_KEY_ENV = "CURSEFORGE_API_KEY"
CURSEFORGE_AWAITING = ("CurseForge-only; awaiting official CurseForge API key "
                       "(allowModDistribution must be true)")
CURSEFORGE_DISALLOWED = ("CurseForge-only; allowModDistribution is false (the author does not allow "
                         "third-party downloads through the official API)")
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
    cf_mod_id: int = 0        # CurseForge project id (the official API addresses mods by id)
    listed_lib: bool = False  # #277 marks it [lib]; kept to compare with the jar's class
    licence: str = ""         # CurseForge-only mods: the licence, read from the source repo
    licence_source: str = ""
    redistribution: str = ""


LIST = Path(__file__).resolve().parent / "data" / "gauntlet_50.json"


def load_list(path: Path = LIST) -> tuple[Listed, ...]:
    """#277's 50, in its order, from ``data/gauntlet_50.json`` (the mods are
    named in a data file, not in core code: tests/test_core_namespace_free)."""
    return tuple(Listed(**entry) for entry in json.loads(Path(path).read_text())["mods"])


THE_50: tuple[Listed, ...] = load_list()


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


_CF_LOADERS = {"Forge": "forge", "NeoForge": "neoforge", "Fabric": "fabric", "Quilt": "quilt"}
_CF_RELEASE_TYPES = {1: "release", 2: "beta", 3: "alpha"}


def curseforge_key() -> str:
    """The official API key from the environment (the repo's Actions secret
    of the same name), or "" when there is none. Never logged."""
    return os.environ.get(CURSEFORGE_KEY_ENV, "").strip()


def _cf_get(path: str, key: str, opener=urllib.request.urlopen):
    """GET an official CurseForge API path. The key travels only in the
    ``x-api-key`` header; errors name the path, never the key."""
    req = urllib.request.Request(f"{CURSEFORGE_API}{path}",
                                 headers={"User-Agent": _USER_AGENT, "Accept": "application/json",
                                          "x-api-key": key})
    try:
        with opener(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise PinError(f"CurseForge API GET {path}: {str(exc).replace(key, '***') if key else exc}") from None


def _cf_builds(files: list) -> list[dict]:
    """Host-neutral builds from the official API's file list. File ids rise
    with upload time, so the id orders the builds (newest first)."""
    out = []
    for f in files or []:
        name = str(f.get("fileName", ""))
        if not name.endswith(".jar") or f.get("isAvailable") is False:
            continue
        tags = f.get("gameVersions") or []
        out.append({"type": _CF_RELEASE_TYPES.get(f.get("releaseType"), "alpha"),
                    "loaders": [_CF_LOADERS[t] for t in tags if t in _CF_LOADERS],
                    "game_versions": [t for t in tags if re.fullmatch(r"\d+\.\d+(\.\d+)?", t)],
                    "date": f"{int(f['id']):012d}", "id": str(f["id"]),
                    "version": f.get("displayName") or name, "filename": name})
    return out


def _cf_files(mod_id: int, key: str, opener) -> list:
    files, index = [], 0
    while True:
        page = _cf_get(f"/mods/{mod_id}/files?index={index}&pageSize=50", key, opener)
        files += page.get("data") or []
        total = (page.get("pagination") or {}).get("totalCount", 0)
        index += 50
        if index >= total or not page.get("data") or index >= 10000:
            return files


def _previous_pins(manifest: Path = MANIFEST) -> dict:
    try:
        return {e["name"]: e for e in tomllib.loads(Path(manifest).read_text()).get("mod", [])}
    except (OSError, ValueError):
        return {}


def pin_curseforge(item: Listed, opener=urllib.request.urlopen, download=None, key: str | None = None,
                   previous: dict | None = None) -> dict:
    """A CurseForge-only mod. Always written ``unfetchable`` (the gate is
    lifted per run by ``gate_curseforge``), with the pinned build as metadata.

    With an API key the build is picked by the version rule from the official
    file list, and hashed once through the API's ``downloadUrl`` only when
    ``allowModDistribution`` is true. Without a key the previous pin is kept
    as it was; nothing is fetched.
    """
    key = curseforge_key() if key is None else key
    prior = dict((previous or {}).get(item.name) or {})
    if not key:
        if prior.get("host") == "curseforge":
            prior.pop("url", None)
            return {**prior, "rank": item.rank, "title": item.title, "cf_mod_id": item.cf_mod_id,
                    "redistribution": item.redistribution, "unfetchable": CURSEFORGE_AWAITING}
        return _unfetchable(item, "curseforge", CURSEFORGE_AWAITING)
    try:
        project = _cf_get(f"/mods/{item.cf_mod_id}", key, opener).get("data") or {}
        builds = _cf_builds(_cf_files(item.cf_mod_id, key, opener))
    except PinError as exc:
        return _unfetchable(item, "curseforge", f"{CURSEFORGE_AWAITING}; API error: {exc}")
    allowed = project.get("allowModDistribution") is True
    chosen = pick(builds) or pick_off_rule(builds)
    if chosen is None:
        return _unfetchable(item, "curseforge", "no Java-loader .jar in the official CurseForge file list")
    build, rule = chosen
    mc, loader = _slot_of(build, rule)
    entry = {
        "name": item.name, "rank": item.rank, "title": item.title, "project": item.curseforge,
        "host": "curseforge", "cf_mod_id": item.cf_mod_id, "version_id": build["id"],
        "version": build["version"], "loader": loader, "minecraft": mc, "rule": rule,
        "license": item.licence or "unknown", "redistribution": item.redistribution,
        "listed_lib": item.listed_lib,
        "unfetchable": CURSEFORGE_AWAITING if allowed else CURSEFORGE_DISALLOWED,
        "notes": f"CurseForge project {item.cf_mod_id}; licence from {item.licence_source}",
    }
    if allowed:
        try:
            url = (_cf_get(f"/mods/{item.cf_mod_id}/files/{build['id']}", key, opener).get("data") or {}).get("downloadUrl")
            if url:
                entry["sha512"] = (download or _sha512_of_url)(url, opener)
        except PinError:
            pass
    if not entry.get("sha512") and prior.get("version_id") == build["id"]:
        entry["sha512"] = prior.get("sha512", "")
    return entry


def purge_curseforge(mods, cache: Path) -> list[Path]:
    """Delete any CurseForge mod's jar from the corpus cache (``<name>-*.jar``).

    CurseForge jars are never cached (#278 pick 2), but a cache restored from
    before that rule (or a hand-run fetch) could still hold one, and Actions
    would save it again. Runs before every gauntlet run; returns what went.
    """
    gone = []
    for mod in mods:
        if getattr(mod, "host", "") != "curseforge" or not Path(cache).is_dir():
            continue
        for jar in Path(cache).glob(f"{mod.name}-*.jar"):
            jar.unlink(missing_ok=True)
            gone.append(jar)
    return gone


def gate_curseforge(mods, key: str | None = None, opener=urllib.request.urlopen, log=print):
    """Lift ``unfetchable`` from CurseForge mods the official API lets us fetch.

    For each ``host = "curseforge"`` mod: with no key it stays unfetchable as
    pinned. With a key, ``allowModDistribution`` is read from
    ``/v1/mods/{id}``; false (or missing) marks it unfetchable with that
    reason; true takes the pinned file's ``downloadUrl`` from
    ``/v1/mods/{id}/files/{fileId}`` and clears the mark, so the run fetches
    it (still sha512-checked against the pin). Returns (mods, {name: allow}).
    """
    key = curseforge_key() if key is None else key
    out, allow = [], {}
    for mod in mods:
        if getattr(mod, "host", "") != "curseforge" or not key:
            out.append(mod)
            continue
        if not getattr(mod, "cf_mod_id", 0) or not mod.version_id:
            out.append(dataclasses.replace(mod, unfetchable=f"{CURSEFORGE_AWAITING}; no CurseForge mod/file id pinned"))
            continue
        try:
            data = _cf_get(f"/mods/{mod.cf_mod_id}", key, opener).get("data") or {}
        except PinError as exc:
            log(f"{mod.name}: CurseForge API error: {exc}")
            out.append(dataclasses.replace(mod, unfetchable=f"{CURSEFORGE_AWAITING}; API error: {exc}"[:300]))
            continue
        allowed = data.get("allowModDistribution")
        allow[mod.name] = allowed
        log(f"{mod.name}: CurseForge mod {mod.cf_mod_id} allowModDistribution={allowed}")
        if allowed is not True:
            out.append(dataclasses.replace(mod, unfetchable=CURSEFORGE_DISALLOWED))
            continue
        try:
            url = (_cf_get(f"/mods/{mod.cf_mod_id}/files/{mod.version_id}", key, opener).get("data") or {}).get("downloadUrl")
        except PinError as exc:
            out.append(dataclasses.replace(mod, unfetchable=f"official API file lookup failed: {exc}"[:300]))
            continue
        if not url:
            out.append(dataclasses.replace(mod, unfetchable="official API gave no downloadUrl for the pinned file"))
            continue
        out.append(dataclasses.replace(
            mod, unfetchable="", url=url,
            redistribution="official CurseForge API (allowModDistribution true); fetched fresh each run, "
                           "measured and discarded, never cached or committed"))
    return out, allow


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
    entry = {"name": item.name, "rank": item.rank, "title": item.title,
             "project": item.modrinth or item.curseforge, "host": host,
             "license": licence or item.licence or "unknown", "listed_lib": item.listed_lib,
             "unfetchable": reason, "redistribution": item.redistribution}
    if item.cf_mod_id:
        entry["cf_mod_id"] = item.cf_mod_id
    return entry


def pin(items=THE_50, opener=urllib.request.urlopen, download=None, log=print,
        key: str | None = None, previous: dict | None = None) -> list[dict]:
    entries = []
    previous = _previous_pins() if previous is None else previous
    for item in items:
        if item.modrinth:
            entry = pin_modrinth(item, opener)
        elif item.curseforge:
            entry = pin_curseforge(item, opener, download, key=key, previous=previous)
        else:
            entry = _unfetchable(item, "", "no host known")
        log(f"{item.rank:2} {item.name}: " + (f"unfetchable: {entry['unfetchable']}" if entry.get("unfetchable")
                                              else f"{entry['minecraft']} {entry['loader']} {entry['version']} ({entry['rule']})"))
        entries.append(entry)
    return entries


_KEYS = ("name", "rank", "title", "project", "host", "cf_mod_id", "version_id", "version", "loader", "minecraft",
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
        "# Modrinth first. CurseForge-only mods stay `unfetchable` here, file id and sha512",
        "# kept as metadata; a run with CURSEFORGE_API_KEY fetches them through the official",
        "# API only when allowModDistribution is true, never from the CDN directly and never",
        "# cached (#278 pick 2). `unfetchable` marks a jar that can't be fetched, with the reason.",
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


# Code facts kept on a profile (portkit.codeonly.facts, #279): the numbers
# classify reads, not the event lists.
_CODE_KEYS = ("classes", "screens", "widgets", "render", "blaze3d", "key_registration", "key_mappings",
              "payloads", "network", "config_screen", "hud", "commands", "event_classes", "gameplay_events",
              "events", "mixins")


def profile(jar: Path | str) -> dict:
    """What the jar holds, read from its own files (no description, no host).

    A jar with no content files also gets its code facts (``code``, from
    :func:`portkit.codeonly.facts`): screens, renderer calls, keybinds,
    events, which separate a library from a UI or gameplay mod (#279).
    """
    with zipfile.ZipFile(jar) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        counts = {k: sum(1 for n in names if p.match(n)) for k, p in _PATTERNS.items()}
        counts["assets"] = sum(1 for n in names if _ASSETS.match(n))
        counts["data"] = sum(1 for n in names if _DATA.match(n))
        counts["api_classes"] = sum(1 for n in names if _API_CLASS.search(n))
        namespaces = sorted({n.split("/")[1] for n in names if _ASSETS.match(n) or _DATA.match(n)})
        meta = _metadata(zf, names)
    prof = {"counts": counts, "namespaces": namespaces, **meta}
    if not any(counts.get(k) for k in _CONTENT_KEYS):
        from . import codeonly

        facts = codeonly.facts(Path(jar))
        prof["code"] = {k: facts.get(k) for k in _CODE_KEYS}
    return prof


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


_FLAG_TEXT = {"language_adapter": "provides a language adapter",
              "modmenu_library_badge": "Mod Menu badge \"library\""}

CLASSES = ("content", "library", "client-only", "performance/mixin-only", "gameplay code", "UI/info")


def classify(prof: dict) -> tuple[str, list[str]]:
    """(class, evidence). The first rule that holds, in this order:

    content     the jar ships game content Bedrock can hold: blockstates, item
                definitions, recipes, loot tables, worldgen or structures.
    library     the jar says it is one (a language adapter, Mod Menu's
                "library" badge), is a bundle of nested module jars (5+ of
                them and at most 10 classes of its own), keeps most of its
                classes in an ``api`` package, defines an event API (10+
                ``*Event(s)`` classes in 100+), is code only (100+ classes,
                no textures, lang or sounds, few mixins, and no gameplay
                event hooks of its own), or is passive (50+ classes, mixins
                under 5%, hooks no game, input, screen or HUD event and
                registers no keybind, and doesn't declare client-only), i.e.
                code other mods call. The last two need the code facts
                (``prof["code"]``, #279).
    client-only the jar declares it runs on one side (Fabric environment
                "client", NeoForge clientSideOnly, a minecraft dependency on
                side CLIENT, or Forge/NeoForge displayTest IGNORE_ALL_VERSION)
                and its code reaches the world renderer, or has no screens:
                rendering, not GUI.
    UI/info     (one-sided) a client-side jar whose code is screens: at least
                one screen class and under 10 classes calling the world
                renderer (#279).
    performance/mixin-only
                mixins are at least 10% of its classes, and it has at most 10
                lang files, 8 textures, no sounds and no shaders.
    gameplay code
                code that hooks gameplay events (blocks broken, players or
                living entities acting) with no screen, HUD or renderer code
                of its own (#279).
    UI/info     everything else: screens, overlays, tooltips, keybinds.
    """
    from .codeonly import library_evidence

    c, flags = prof["counts"], set(prof.get("flags") or ())
    content = [f"{k} {c[k]}" for k in _CONTENT_KEYS if c.get(k)]
    if content:
        return "content", content
    code = prof.get("code") or {}
    classes = c.get("classes", 0)
    mixins = sum((prof.get("mixin_classes") or {}).values())
    share = mixins / classes if classes else 0.0
    facts = {**code, "flags": sorted(flags), "classes": classes, "nested_jars": c.get("nested_jars", 0),
             "api_classes": c.get("api_classes", 0), "mixins": mixins, "environment": prof.get("environment"),
             "textures": c.get("textures", 0)}
    lib = library_evidence(facts) if code else [
        e for e in library_evidence({**facts, "events": ["?"]})]  # no code facts: never "passive"
    hooks = bool(code.get("gameplay_events")) and code.get("event_classes", 0) < 10
    if (classes >= 100 and not c.get("textures") and not c.get("lang") and not c.get("sounds")
            and share < 0.10 and not hooks):
        lib.append(f"code only: {classes} classes, no textures, lang or sounds, {mixins} mixin(s)")
    if lib:
        return "library", lib
    one_sided = ("declares client-only" if prof.get("environment") == "client" else
                 "one-sided: displayTest IGNORE_ALL_VERSION" if "display_test_ignore_all" in flags else "")
    if one_sided:
        if code.get("screens") and code.get("render", 0) < 10:
            return "UI/info", [one_sided, f"{code['screens']} screen class(es), {code.get('render', 0)} "
                                          "class(es) calling the world renderer"]
        return "client-only", [one_sided]
    if (prof.get("mixin_configs") and share >= 0.10 and c.get("lang", 0) <= 10
            and c.get("textures", 0) <= 8 and not c.get("sounds") and not c.get("shaders")):
        return "performance/mixin-only", [f"{mixins} mixin(s) in {classes} classes "
                                          f"({len(prof['mixin_configs'])} config(s))",
                                          f"lang {c.get('lang', 0)}, textures {c.get('textures', 0)}"]
    if (code.get("gameplay_events") and not code.get("screens") and not code.get("hud")
            and code.get("render", 0) < 10):
        events = code["gameplay_events"]
        return "gameplay code", ["hooks " + ", ".join(events[:3]) + (" …" if len(events) > 3 else ""),
                                 f"no screens, HUD or renderer code; {classes} classes"]
    return "UI/info", [f"textures {c.get('textures', 0)} (gui {c.get('gui_textures', 0)})",
                       f"lang {c.get('lang', 0)}", f"{mixins} mixin(s) in {classes} classes",
                       f"environment {prof.get('environment')}"]


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
        parts = m.group(1).strip("/").split("/")[:3]
        if len(parts) == 3 and "." in parts[2]:  # a file right under assets/<ns>/ (icon.png, *.properties)
            parts = parts[:2]
        return f"{kind} [{'/'.join(parts)}/]"
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
               "counts": prof.get("counts", {}), "listed_lib": rec.get("listed_lib", False),
               "outcome": rec.get("outcome"), "explained_by": rec.get("reason_classes") or []}
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
    # Why nothing converts, across the explained-empty mods (#279).
    empty_roll: dict[str, dict] = {}
    for m in mods:
        for r in m["explained_by"]:
            slot = empty_roll.setdefault(r["class"], {"reason_class": r["class"], "mods": 0, "mod_names": []})
            slot["mods"] += 1
            slot["mod_names"].append(m["name"])
    explained_empty = sorted(empty_roll.values(), key=lambda r: (-r["mods"], r["reason_class"]))
    ok = [m for m in mods if m["status"] == "ok" and m["coverage"] is not None]
    return {
        "schema": SCHEMA, "kind": "gauntlet-board", "generated": lb["generated"],
        "manifest": lb["manifest"], "mods_total": len(mods), "statuses": lb["statuses"],
        "classes": {k: classes[k] for k in (*CLASSES, *sorted(set(classes) - set(CLASSES))) if classes.get(k)},
        "done": sum(1 for m in mods if m["done"]),
        "explained_empty": sum(1 for m in mods if m.get("outcome") == "explained-empty"),
        "explained_empty_rollup": explained_empty,
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
                                 "done": m["done"], **({"outcome": m["outcome"]} if m.get("outcome") else {})}
                     for m in b["mods"]}}


def _cell(text) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def _mct(m) -> str:
    mct = m.get("mct")
    if not isinstance(mct, dict):
        return ""
    if "failed" in mct:
        return "failed"
    if "skipped" in mct:
        return "no pack"
    return f"{mct.get('error', 0)}/{mct.get('warning', 0)}"


def _validate(m) -> str:
    if m["status"] != "ok":
        return ""
    if m.get("outcome") == "explained-empty" and not m.get("errors"):
        return "explained-empty"
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
              f"Done under #277 rule 6 (converted, validator clean, every residue explained): {b['done']} of {b['mods_total']}"
              + (f", {b['explained_empty']} of them explained-empty (nothing convertible, no pack; #279)."
                 if b.get("explained_empty") else "."),
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
    if b.get("explained_empty_rollup"):
        lines += ["", "## Why nothing converts (explained-empty, #279)", "",
                  "Mods with nothing Bedrock can hold get no pack and an `explained-empty.json` naming the "
                  "reason classes read from the jar (`portkit.codeonly`); their lang and asset leftovers are "
                  "`code_only` residue. A mod counts under every class its jar shows.", "",
                  "| reason class | mods | mods |", "|---|---:|---|"]
        for r in b["explained_empty_rollup"]:
            lines.append(f"| {r['reason_class']} | {r['mods']} | {_cell(', '.join(r['mod_names']))} |")
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
              "client-only, performance/mixin-only, UI/info; `portkit.gauntlet.classify`).", "",
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
