"""Build the random-sample manifest (#234) from Modrinth's own data.

``portkit sample build`` asks Modrinth's public API for the most-downloaded
mods, keeps the ones that look like they carry content (see ``is_content``),
pins each one's newest Java-loader version by version id, primary file url
and sha512 (Modrinth publishes sha1 and sha512, not sha256), and writes a
manifest in the corpus format (``fixtures/real/mods.toml``) so
``portkit.corpus`` can load and fetch it unchanged.

Every field comes from the API response; nothing is typed in by hand. The
header records the query, the date and the filter, so the sample can be
rebuilt and diffed.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date

API = "https://api.modrinth.com/v2"
_USER_AGENT = "anchapin/portkit-v2 sample build (github.com/anchapin/portkit-v2)"
LOADERS = ("fabric", "forge", "neoforge", "quilt")
# The search facet project_type=mod (Modrinth writes facets as "key:value").
_MODS_ONLY = ("project_type", "mod")

# Modrinth categories that say a mod adds things to the game. A mod tagged
# only with loaders, "library", "optimization", "utility", "management",
# "social" or "cursed" has nothing for the converter to work on, and the raw
# download ranking is dominated by those (Fabric API, Sodium, Iris...).
# DEFAULT (#234 design pick 3): content categories, not a library, not
# client-only (server_side "unsupported").
CONTENT_CATEGORIES = frozenset({
    "adventure", "decoration", "economy", "equipment", "food", "game-mechanics",
    "magic", "minigame", "mobs", "storage", "technology", "transportation", "worldgen",
})

# DEFAULT (#234 design pick 1): "all" keeps every licence, as the corpus does
# (Waystones is All Rights Reserved, Create and Supplementaries use custom
# licences): jars are downloaded from Modrinth's CDN, measured and discarded,
# never committed or redistributed. "open" keeps SPDX ids only, dropping
# LicenseRef-* (All Rights Reserved and custom licences).
LICENCE_POLICIES = ("all", "open")


class SampleError(Exception):
    """The API answered with something we can't use."""


def _get(path: str, params: dict | None = None, opener=urllib.request.urlopen):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise SampleError(f"GET {url}: {exc}") from exc


def is_content(hit: dict) -> bool:
    cats = set(hit.get("categories") or ())
    return (hit.get("server_side") != "unsupported"
            and "library" not in cats
            and bool(cats & CONTENT_CATEGORIES))


def licence_allowed(licence: str, policy: str) -> bool:
    if policy == "all":
        return True
    if policy == "open":
        return bool(licence) and not licence.startswith("LicenseRef-")
    raise ValueError(f"unknown licence policy {policy!r}")


def top_projects(count: int, policy: str = "all", opener=urllib.request.urlopen,
                 page: int = 100, max_scan: int = 2000) -> list[tuple[int, dict]]:
    """(download rank, search hit) for the first ``count`` content mods."""
    out, offset = [], 0
    while len(out) < count and offset < max_scan:
        data = _get("/search", {"index": "downloads", "limit": page, "offset": offset,
                                "facets": json.dumps([[":".join(_MODS_ONLY)]])}, opener)
        hits = data.get("hits") or []
        if not hits:
            break
        for i, hit in enumerate(hits):
            if is_content(hit) and licence_allowed(hit.get("license") or "", policy):
                out.append((offset + i + 1, hit))
                if len(out) == count:
                    break
        offset += page
    return out


def pick_version(versions: list[dict]) -> tuple[dict, dict] | None:
    """The newest version with a Java-loader primary .jar: (version, file).

    Modrinth lists a project's versions newest first. Release builds are
    preferred; a project that only publishes betas (Mythic Metals does) gets
    its newest beta.
    """
    def usable(v):
        if not set(v.get("loaders") or ()) & set(LOADERS):
            return None
        files = v.get("files") or []
        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not primary or not str(primary.get("filename", "")).endswith(".jar"):
            return None
        if not (primary.get("hashes") or {}).get("sha512"):
            return None
        return v, primary

    candidates = [u for u in map(usable, versions) if u]
    for v, f in candidates:
        if v.get("version_type") == "release":
            return v, f
    return candidates[0] if candidates else None


def _loader(version: dict) -> str:
    loaders = [x for x in LOADERS if x in (version.get("loaders") or ())]
    return loaders[0] if loaders else ""


def _name(slug: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", slug.lower()).strip("_")


def build(count: int, policy: str = "all", opener=urllib.request.urlopen,
          today: str | None = None) -> tuple[list[dict], list[str]]:
    """(manifest entries, notes on projects skipped). Entries are dicts with
    the corpus manifest keys."""
    entries, skipped = [], []
    for rank, hit in top_projects(count, policy, opener):
        versions = _get(f"/project/{hit['project_id']}/version", None, opener)
        picked = pick_version(versions if isinstance(versions, list) else [])
        if picked is None:
            skipped.append(f"{hit['slug']}: no version with a Java-loader .jar")
            continue
        version, file = picked
        games = version.get("game_versions") or []
        entries.append({
            "name": _name(hit["slug"]),
            "project": hit["slug"],
            "version_id": version["id"],
            "version": version.get("version_number", ""),
            "loader": _loader(version),
            "minecraft": games[-1] if games else "",
            "license": hit.get("license") or "unknown",
            "url": file["url"],
            "sha512": file["hashes"]["sha512"],
            "notes": (f"download rank {rank} on Modrinth ({hit.get('downloads', 0)} downloads, "
                      f"{today or date.today().isoformat()}); categories: "
                      f"{', '.join(c for c in hit.get('categories', []) if c not in LOADERS)}"),
        })
    return entries, skipped


def _toml_str(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def render(entries: list[dict], count: int, policy: str, today: str) -> str:
    head = [
        "# The random-sample corpus (#234): popular Modrinth mods, measured for the gap",
        "# leaderboard. Same format as fixtures/real/mods.toml; jars are downloaded and",
        "# sha512-checked, never committed. Generated, not hand-edited:",
        f"#   portkit sample build --count {count} --licences {policy} --out fixtures/sample/mods.toml",
        f"# Built {today} from api.modrinth.com/v2/search?index=downloads (project_type:mod),",
        "# keeping content mods (a content category, not a library, not client-only) and",
        "# pinning each one's newest release with a Fabric/Forge/NeoForge/Quilt .jar.",
        "# license is the project's declared licence on Modrinth.",
        "",
    ]
    body = []
    for e in entries:
        body.append("[[mod]]")
        for key in ("name", "project", "version_id", "version", "loader", "minecraft",
                    "license", "url", "sha512", "notes"):
            body.append(f"{key} = {_toml_str(e[key])}")
        body.append("")
    return "\n".join(head + body)
