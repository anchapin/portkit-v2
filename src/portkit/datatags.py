"""Leftover data tags (#293): put them where Bedrock reads them, or say why not.

A tag file under ``data/<ns>/tags/`` that no converter read is ``unowned``
residue (:func:`portkit.pipeline.unowned`). The recipe converter already claims
the item tags its recipes read (:class:`portkit.converters.tags.TagResolver`),
and gives the mod's members of a Bedrock vanilla item tag that tag
(``minecraft:planks``). Two more things a Bedrock pack can hold come from tags:

* **Tool and tier tags on blocks.** Java says which tool mines a block fast
  (``minecraft:mineable/pickaxe``) and which tier it needs to drop
  (``minecraft:needs_iron_tool``) only through block tags. Bedrock says the same
  through vanilla block tags a block carries: ``minecraft:is_pickaxe_item_destructible``
  and ``minecraft:iron_tier_destructible`` (learn.microsoft.com, Block Documentation
  - Vanilla Block Tags and - tag:; out of experiments since Bedrock 1.21.50,
  feedback.minecraft.net "Minecraft: Bedrock Edition 1.21.50"). :func:`tool_tags`
  adds them to the blocks the pack ships and claims the tag files.
  Bedrock's shears and sword tags are left out (they don't work,
  wiki.bedrock.dev Tool-Based Destruction, MCPE-189586), and so are Forge's wood
  and gold tiers, which Bedrock removed in 1.21.50.

* Everything else is explained from the jar's own files by :func:`refine`:

  - ``tag_unshipped_registry``: a tag of a registry portkit converts nothing of
    (fluids, biomes, structures, enchantments, damage types, banner patterns,
    entity types, ...), so the pack has nothing it could group;
  - ``owned_by_residue``: a data file of the jar that is residue names the tag
    (a machine recipe, a loot table no converter wrote), or every member from
    this jar is residue: the tag applies when they convert;
  - ``tag_unread``: its members ship, but no data file of the jar reads it
    (only the mod's Java code, or other mods, do), and Bedrock has no tag of the
    name its own systems read; or it names only vanilla entries (an add-on
    can't re-tag vanilla items) and other mods' entries the addon can't hold.

  A tag a shipped file names that still wasn't claimed is a converter gap and
  stays ``unowned``.

Memberships are read from the jar's own tag files (nested tags expanded through
the jar's files, Forge/NeoForge ``remove`` applied as
:func:`portkit.converters.tags.removals` says). Vanilla's and the loader's own
shares aren't needed: the question is only which of *this* jar's entries are in
the tag. Nothing here names a mod.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .converters.tags import entry_ref, removals
from .model import Unhandled

UNSHIPPED_REGISTRY = "tag_unshipped_registry"
UNREAD = "tag_unread"
OWNED = "owned_by_residue"
KINDS = frozenset({UNSHIPPED_REGISTRY, UNREAD})

# Registry folders of the tags portkit can act on (pre-1.21 plural, 1.21 singular).
_ITEM_DIRS = ("items", "item")
_BLOCK_DIRS = ("blocks", "block")
_CONVERTED = frozenset(_ITEM_DIRS + _BLOCK_DIRS)

# Java block tag -> the Bedrock vanilla block tag that means the same.
# Bedrock: learn.microsoft.com "Block Documentation - Vanilla Block Tags";
# wiki.bedrock.dev "Tool-Based Destruction" (what each one does).
# Java: minecraft.wiki "Tag (Java Edition)" (mineable/*, needs_*_tool);
# Forge 1.20.1's forge:needs_netherite_tool (Tags.Blocks.NEEDS_NETHERITE_TOOL).
TOOL_TAGS = {
    "minecraft:mineable/pickaxe": "minecraft:is_pickaxe_item_destructible",
    "minecraft:mineable/axe": "minecraft:is_axe_item_destructible",
    "minecraft:mineable/shovel": "minecraft:is_shovel_item_destructible",
    "minecraft:mineable/hoe": "minecraft:is_hoe_item_destructible",
    "minecraft:needs_stone_tool": "minecraft:stone_tier_destructible",
    "minecraft:needs_iron_tool": "minecraft:iron_tier_destructible",
    "minecraft:needs_diamond_tool": "minecraft:diamond_tier_destructible",
    "forge:needs_netherite_tool": "minecraft:netherite_tier_destructible",
}

# Block format 1.26.20 removed ``tag:*`` components (bedrock.dev Block Format
# History); a block at that format or later is left untagged.
_TAG_COMPONENT_LAST = (1, 26, 20)


def _version(text) -> tuple:
    try:
        return tuple(int(p) for p in str(text).split("."))
    except ValueError:
        return ()


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _tag_path(root: Path, tag: str, dirs: tuple[str, ...]) -> Path | None:
    ns, _, path = tag.partition(":")
    if not path:
        return None
    for folder in dirs:
        candidate = root / "data" / ns / "tags" / folder / f"{path}.json"
        if candidate.is_file():
            return candidate
    return None


def jar_members(root: Path, tag: str, dirs: tuple[str, ...], loader: str | None,
                read: list[str] | None = None, _seen: frozenset = frozenset()) -> list[str] | None:
    """The ids the jar's own files put in ``tag`` (nested tags through the
    jar's files, Forge/NeoForge ``remove`` applied), or None when its file
    removes entries and the jar declares no loader. ``read`` collects the tag
    files read, root-relative."""
    path = _tag_path(root, tag, dirs)
    if path is None:
        return []
    data = _read(path)
    if not isinstance(data, dict):
        return []
    if read is not None:
        read.append(path.relative_to(root).as_posix())
    try:
        removed = removals(data, loader)
    except ValueError:
        return None
    seen = _seen | {tag}
    members: list[str] = []
    for entry in data.get("values") or []:
        ref = entry_ref(entry)
        if ref is None:
            continue
        if ref.startswith("#"):
            if ref[1:] in seen:
                continue
            nested = jar_members(root, ref[1:], dirs, loader, read, seen)
            if nested is None:
                return None
            members.extend(m for m in nested if m not in members)
        elif ref not in members:
            members.append(ref)
    for entry in removed:
        ref = entry_ref(entry)
        if ref is None:
            continue
        if ref.startswith("#"):
            gone = jar_members(root, ref[1:], dirs, loader, read, seen) or []
        else:
            gone = [ref]
        members = [m for m in members if m not in gone]
    return members


def jar_namespaces(root: Path) -> set[str]:
    """The namespaces the jar ships under assets/ and data/, shared ones excluded."""
    found: set[str] = set()
    for top in ("assets", "data"):
        folder = Path(root) / top
        if folder.is_dir():
            found |= {p.name for p in folder.iterdir() if p.is_dir()}
    return found - {"minecraft", "c", "forge", "neoforge", "fabric"}


def _block_paths(files: dict) -> dict[str, str]:
    """identifier -> pack path of every block definition the pack ships."""
    found: dict[str, str] = {}
    for path, body in files.items():
        if not (path.startswith("blocks/") and path.endswith(".json") and isinstance(body, dict)):
            continue
        block = body.get("minecraft:block")
        ident = ((block or {}).get("description") or {}).get("identifier") if isinstance(block, dict) else None
        if isinstance(ident, str):
            found[ident] = path
    return found


def tool_tags(root: Path, files: dict, loader: str | None) -> tuple[set[str], list[str]]:
    """Give the pack's blocks the Bedrock tool and tier tags their Java block
    tags say. Edits ``files`` in place; returns (tag files claimed, notes)."""
    root = Path(root)
    blocks = _block_paths(files)
    claimed: set[str] = set()
    notes: list[str] = []
    if not blocks:
        return claimed, notes
    per_block: dict[str, list[tuple[str, str]]] = {}
    for java_tag, bedrock_tag in TOOL_TAGS.items():
        read: list[str] = []
        members = jar_members(root, java_tag, _BLOCK_DIRS, loader, read)
        if not members:
            continue
        hit = [m for m in members if m in blocks]
        if not hit:
            continue
        for member in hit:
            per_block.setdefault(member, []).append((java_tag, bedrock_tag))
        claimed.update(read)
    skipped: list[str] = []
    tagged = 0
    for ident, pairs in sorted(per_block.items()):
        path = blocks[ident]
        body = files[path]
        if _version(body.get("format_version")) >= _TAG_COMPONENT_LAST:
            skipped.append(ident)
            continue
        components = body["minecraft:block"].setdefault("components", {})
        for _, bedrock_tag in pairs:
            components.setdefault(f"tag:{bedrock_tag}", {})
        tagged += 1
    if tagged:
        notes.append(f"{tagged} block(s) carry Bedrock's tool/tier block tags from their Java block tags "
                     f"({', '.join(sorted({j for p in per_block.values() for j, _ in p}))})")
    if skipped:
        notes.append(f"{len(skipped)} block(s) at block format 1.26.20 or later, which has no tag:* "
                     f"components, keep no tool/tier tag: {', '.join(skipped[:5])}"
                     + (f" and {len(skipped) - 5} more" if len(skipped) > 5 else ""))
    return claimed, notes


# -- explaining what's left -------------------------------------------------

_TAG_FILE = re.compile(r"^data/([^/]+)/tags/(.+)\.json$")
_ADVANCEMENT = re.compile(r"^data/[^/]+/advancements?/")
_ITEM_READERS = re.compile(r"^data/[^/]+/(recipes?|advancements?)/")
_ID = re.compile(r"^#?[a-z0-9_.\-]+:[a-z0-9_./\-]+$")


def _split(rel: str) -> tuple[str, str, str] | None:
    """(namespace, registry folder, tag path) of a tag file. A registry is one
    folder (``item``), two under ``worldgen/``, or ``<ns>/<path>`` for another
    mod's registry (NeoForge's layout for non-Minecraft registries)."""
    m = _TAG_FILE.match(rel)
    if not m:
        return None
    ns, rest = m.groups()
    parts = rest.split("/")
    if len(parts) < 2:
        return None
    width = 2 if parts[0] == "worldgen" and len(parts) > 2 else 1
    return ns, "/".join(parts[:width]), "/".join(parts[width:])


def _tag_refs(root: Path) -> dict[str, set[str]]:
    """tag id -> the jar's data files (outside tags/) naming it, as ``#id`` or
    under a ``tag`` key."""
    found: dict[str, set[str]] = {}
    data = root / "data"
    if not data.is_dir():
        return found

    def walk(value, key, rel):
        if isinstance(value, str):
            if value.startswith("#") and _ID.match(value):
                found.setdefault(value[1:], set()).add(rel)
            elif key == "tag" and _ID.match(value):
                found.setdefault(value, set()).add(rel)
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(v, str(k), rel)
        elif isinstance(value, list):
            for v in value:
                walk(v, key, rel)

    for path in sorted(data.rglob("*.json")):
        rel = path.relative_to(root).as_posix()
        if "/tags/" in rel:
            continue
        doc = _read(path)
        if doc is not None:
            walk(doc, "", rel)
    return found


def classify(root: Path, files: list[str], consumed: set[str], residue_sources: set[str],
             shipped: set[str], namespaces: set[str], loader: str | None,
             pack_paths: set[str] | None = None) -> dict[str, tuple[str, str]]:
    """tag file -> (kind, detail) for the leftover tag files the jar explains;
    a tag a shipped file names is left out (a converter gap)."""
    root = Path(root)
    refs = _tag_refs(root)
    has_entities = any(p.startswith("entities/") for p in (pack_paths or ()))
    out: dict[str, tuple[str, str]] = {}
    for rel in files:
        split = _split(rel)
        if split is None:
            continue
        ns, registry, path = split
        tag = f"{ns}:{path}"
        if registry not in _CONVERTED:
            if registry in ("entity_type", "entity_types") and has_entities:
                continue  # the pack has entities: a converter could have used it
            out[rel] = (UNSHIPPED_REGISTRY, registry)
            continue
        users = refs.get(tag, set())
        if registry in _BLOCK_DIRS:
            # Recipes and their advancements take item tags; a block tag of the
            # same name isn't what they read.
            users = {u for u in users if not _ITEM_READERS.match(u)}
        residue_users = sorted(u for u in users if u in residue_sources or u not in consumed)
        if residue_users:
            out[rel] = (OWNED, residue_users[0])
            continue
        # A shipped recipe that takes the tag has the recipe converter read it
        # (claimed already), and a recipe advancement read for its unlock that
        # names it only drops that criterion. Any other shipped file naming it
        # (a loot table's tool check, ...) means a converter missed it: a gap.
        if any(u in consumed and not _ADVANCEMENT.match(u) for u in users):
            continue
        dirs = _ITEM_DIRS if registry in _ITEM_DIRS else _BLOCK_DIRS
        members = jar_members(root, tag, dirs, loader)
        if members is None:
            continue
        own = [m for m in members if m.partition(":")[0] in namespaces and m.partition(":")[0] != "minecraft"]
        if own and not any(m in shipped for m in own):
            out[rel] = (OWNED, f"{len(own)} member(s) of this jar, none shipped")
            continue
        out[rel] = (UNREAD, "members" if own else "foreign")
    return out


def _group(rel: str) -> str:
    split = _split(rel)
    if split is None:
        return rel
    ns, registry, _ = split
    return f"data/{ns}/tags/{registry}/"


def _registry_name(registry: str) -> str:
    return registry.replace("_", " ").replace("/", " ")


def refine(unhandled: list[Unhandled], root: Path, consumed: set[str], shipped: set[str],
           namespaces: set[str], loader: str | None, pack_paths: set[str] | None = None) -> list[Unhandled]:
    """Re-file the unowned tag files the jar explains; the rest of the residue
    is returned unchanged."""
    groups = [u for u in unhandled if u.kind == "unowned" and re.match(r"^data/[^/]+/tags/", u.source)]
    if not groups:
        return unhandled
    root = Path(root)
    leftover: list[str] = []
    for u in groups:
        base = root / u.source.rstrip("/")
        if base.is_dir():
            leftover += [p.relative_to(root).as_posix() for p in sorted(base.rglob("*.json"))
                         if p.is_file() and p.relative_to(root).as_posix() not in consumed]
    sources = {u.source for u in unhandled if u.kind != "unowned"}
    found = classify(root, leftover, consumed, sources, shipped, namespaces, loader, pack_paths)

    entries: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for rel, (kind, detail) in sorted(found.items()):
        entries.setdefault((kind, _group(rel)), []).append((rel, detail))
    refiled: list[Unhandled] = []
    for (kind, group), members in sorted(entries.items()):
        n = len(members)
        sample = ", ".join(r.rsplit("/", 1)[-1][:-5] for r, _ in members[:3])
        if kind == UNSHIPPED_REGISTRY:
            registry = _registry_name(members[0][1])
            reason = (f"{n} {registry} tag(s): portkit converts nothing of the {registry} registry, so the "
                      f"pack holds nothing these could group (e.g. {sample})")
        elif kind == OWNED:
            owners = sorted({d for _, d in members if "/" in d})
            unshipped = sum(1 for _, d in members if "/" not in d)
            parts = []
            if owners:
                shown = ", ".join(owners[:3]) + (f" and {len(owners) - 3} more" if len(owners) > 3 else "")
                parts.append(f"named only by residue that has its own entry ({shown})")
            if unshipped:
                parts.append(f"{unshipped} whose every member from this jar is residue")
            reason = (f"{n} tag(s) {'; '.join(parts)}: they apply when their owner or members convert "
                      f"(e.g. {sample})")
        else:
            foreign = sum(1 for _, d in members if d == "foreign")
            reason = (f"{n} tag(s) no data file of the jar reads (only the mod's Java code or other mods "
                      f"would), and Bedrock has no tag of the name its own systems read"
                      + (f"; {foreign} name only vanilla entries, which an add-on can't re-tag, or other "
                         f"mods' entries the addon can't hold" if foreign else "")
                      + f" (e.g. {sample})")
        refiled.append(Unhandled(source=group, kind=kind, reason=reason, count=n))

    gone = set(found)
    out: list[Unhandled] = []
    for u in unhandled:
        if u not in groups:
            out.append(u)
            continue
        left = sum(1 for f in leftover if f.startswith(u.source) and f not in gone)
        if left:
            out.append(Unhandled(source=u.source, kind="unowned",
                                 reason=f"{left} file(s) no converter claims yet", count=left))
    return out + refiled
