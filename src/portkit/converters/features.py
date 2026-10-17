"""Java ore features to Bedrock features and feature rules (#281, first slice).

Java builds an ore from three data files: a ``worldgen/configured_feature``
of type ``minecraft:ore`` (what the vein is), a ``worldgen/placed_feature``
(how many veins a chunk gets and where), and, on Forge and NeoForge, a biome
modifier ``data/<ns>/{forge,neoforge}/biome_modifier/*.json`` of type
``<loader>:add_features`` that adds the placed feature to biomes at a
generation step. Bedrock builds the same thing from two: a
``features/<name>.json`` ``minecraft:ore_feature`` and a
``feature_rules/<name>.json`` that attaches it to biomes with a placement pass
and a scatter distribution (Mojang/bedrock-samples documentation/Features.html,
"Attaching features": "Features must be attached to at least one biome in
order to show up in the world ... via a feature rule definition").

The slice reads only biome modifiers whose every feature is a vanilla
``minecraft:ore`` placed with vanilla placement modifiers. Anything else in
them (a feature or placement typed with the mod's own code, geodes, patches,
trees) leaves the modifier untouched for the other passes (``code_worldgen``,
``unowned``). Inside the slice, each placed feature either converts exactly
(per the tables below and ``portkit.data.worldgen``) or goes to residue kind
``worldgen_feature`` with the reason; nothing is guessed (#87).

Mapping (citations: Features.html, "minecraft:ore_feature", "Feature rules",
"Coordinate Range", "Scatter Params"; MicrosoftDocs/minecraft-creator
FeaturesIntroduction.md and Features/minecraftOre_feature.md):

* ``config.size`` -> ``count`` ("The number of blocks to be placed"). Java's
  size bounds the vein's block count; Mojang's own coal example uses count 17,
  vanilla Java coal's size (pick 1).
* ``config.discard_chance_on_air_exposure`` -> the Bedrock field of the same
  name ("Chance of discarding placement if neighboring block is Air", 0..1).
* each ``config.targets`` entry -> a ``replace_rules`` entry, in order (both
  editions try the targets in order; Bedrock: "replace rules that will be
  checked in order of definition"): ``state.Name`` -> ``places_block`` (a block
  the pack ships, no block-state properties); ``block_match`` -> ``may_replace``
  that block; ``tag_match`` of a vanilla ore-replaceable tag -> its members.
* ``minecraft:count`` (a constant) -> ``distribution.iterations``.
* ``minecraft:in_square`` -> ``x`` and ``z`` uniform over ``[0, 15]`` (Java
  adds ``nextInt(16)``; Bedrock extents are inclusive, the scatter example
  uses ``[0, 15]``); without it ``x`` and ``z`` are 0.
* ``minecraft:height_range`` -> ``y``: ``uniform`` -> ``uniform`` over
  ``[min, max]`` (both inclusive); ``trapezoid`` with no plateau ->
  ``triangle`` over ``[min, max]`` (pick 2; a plateau stays residue). Anchors:
  ``absolute``; ``above_bottom`` and ``below_top`` against each edition's
  dimension bounds, residue where they differ (the Nether's top, pick 4).
* ``minecraft:rarity_filter`` -> ``scatter_chance`` 1/N, only where it comes
  before any count or the count is 1 (Bedrock checks the chance once for all
  iterations: "The 'scatter_chance' check happens once").
* ``minecraft:biome`` -> nothing more: the rule's biome filter is the biome set
  (Java's filter keeps the feature to biomes that list it, i.e. the modifier's).
* the modifier's ``biomes``: a vanilla tag of ``BIOME_TAGS`` (or a list of
  them) -> ``minecraft:biome_filter``; its ``step`` -> ``placement_pass``.
* a ``remove_features`` modifier naming the feature -> residue (pick 6): the
  Bedrock rule can't subtract biomes the Java removal names.

Fabric adds features to biomes in code (``BiomeModifications``): those calls
are read from the bytecode by :mod:`portkit.biomecode` (pick 5a) and come in
as ``code`` rows shaped like a modifier, decided the same way; a call that
can't be read exactly leaves its ore ``unowned`` or residue with the reason.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..data import worldgen as ref
from ..model import Unhandled

KIND = "worldgen_feature"
FEATURE_FORMAT = "1.13.0"
RULE_FORMAT = "1.13.0"

_MODIFIER = re.compile(r"^data/([^/]+)/(forge|neoforge)/biome_modifier/(.+)\.json$")
_ADD = {"forge:add_features", "neoforge:add_features"}
_REMOVE = {"forge:remove_features", "neoforge:remove_features"}
_VANILLA_PLACEMENTS = {"minecraft:count", "minecraft:in_square", "minecraft:height_range",
                       "minecraft:rarity_filter", "minecraft:biome"}


@dataclass
class FeatureResult:
    files: dict[str, dict] = field(default_factory=dict)
    consumed: set[str] = field(default_factory=set)
    unhandled: list[Unhandled] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # One row per converted rule, for the in-game check (#281).
    ores: list[dict] = field(default_factory=list)
    geodes: list[dict] = field(default_factory=list)


class _Refused(Exception):
    pass


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _split(ident: str) -> tuple[str, str]:
    ns, _, path = ident.partition(":") if ":" in ident else ("minecraft", "", ident)
    return ns, path


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    return [value] if value is not None else []


def _placements(pf: dict) -> list[dict]:
    return [p for p in pf.get("placement") or [] if isinstance(p, dict)]


def _in_slice(root: Path, ident: str) -> tuple[str, str, dict, dict] | None:
    """(placed rel, configured rel, placed, configured) for a placed feature
    of a vanilla ore with vanilla placements, else None."""
    found = _read_placed(root, ident)
    if found is None:
        return None
    prel, crel, pf, cf = found
    if cf.get("type") != "minecraft:ore":
        return None
    if any(p.get("type") not in _VANILLA_PLACEMENTS for p in _placements(pf)):
        return None
    return prel, crel, pf, cf


def _read_placed(root: Path, ident) -> tuple[str, str, dict, dict] | None:
    if not isinstance(ident, str):
        return None
    ns, path = _split(ident)
    prel = f"data/{ns}/worldgen/placed_feature/{path}.json"
    pf = _read(root / prel)
    if not isinstance(pf, dict) or not isinstance(pf.get("feature"), str):
        return None
    cns, cpath = _split(pf["feature"])
    crel = f"data/{cns}/worldgen/configured_feature/{cpath}.json"
    cf = _read(root / crel)
    if not isinstance(cf, dict):
        return None
    return prel, crel, pf, cf


def _vanilla_placements(placements) -> bool:
    """Every placement modifier is Minecraft's own (a ``minecraft:`` type):
    a mod's placement type is its code, left for ``code_worldgen``."""
    if not isinstance(placements, list):
        return False
    return all(isinstance(p, dict) and isinstance(p.get("type"), str) and p["type"].startswith("minecraft:")
               for p in placements)


def _patch_files(root: Path, cf: dict, seen: set[str], coded: set[str], depth: int = 0) -> bool:
    """Whether ``cf`` is wholly the plant patch family (``ref.PATCH_TYPES``,
    selectors of them) with Minecraft's placements, nested features of the
    mod's own types aside: those (a feature or placement type in a namespace
    other than ``minecraft``, i.e. the mod's code) go into ``coded``, the
    configured and placed feature files it names by id into ``seen``."""
    if depth > 8 or not isinstance(cf, dict):
        return False
    kind = cf.get("type")
    if depth and isinstance(kind, str) and ":" in kind and not kind.startswith("minecraft:"):
        coded.add(kind)
        return True
    config = cf.get("config")
    if not isinstance(config, dict):
        return False
    if kind == "minecraft:simple_block":
        return True
    if kind in ref.PATCH_TYPES:
        return _patch_placed(root, config.get("feature"), seen, coded, depth)
    if kind in ref.SELECTOR_TYPES:
        entries = config.get("features")
        if not isinstance(entries, list) or not entries:
            return False
        placed = [e.get("feature") if kind == "minecraft:random_selector" and isinstance(e, dict) else e
                  for e in entries]
        if kind == "minecraft:random_selector":
            placed.append(config.get("default"))
        return all(_patch_placed(root, p, seen, coded, depth) for p in placed)
    return False


def _patch_placed(root: Path, placed, seen: set[str], coded: set[str], depth: int) -> bool:
    if isinstance(placed, str):
        ns, path = _split(placed)
        rel = f"data/{ns}/worldgen/placed_feature/{path}.json"
        seen.add(rel)
        placed = _read(root / rel)
    if not isinstance(placed, dict) or not isinstance(placed.get("placement", []), list):
        return False
    for p in placed.get("placement", []):
        kind = p.get("type") if isinstance(p, dict) else None
        if not isinstance(kind, str):
            return False
        if not kind.startswith("minecraft:"):
            coded.add(kind)
    feature = placed.get("feature")
    if isinstance(feature, str):
        ns, path = _split(feature)
        rel = f"data/{ns}/worldgen/configured_feature/{path}.json"
        seen.add(rel)
        feature = _read(root / rel)
    return _patch_files(root, feature, seen, coded, depth + 1)


def _classify(root: Path, ident) -> tuple[str, tuple[str, str, dict, dict], set[str], set[str]] | None:
    """(kind, (placed rel, configured rel, placed, configured), nested files,
    nested code types) for a placed feature this module reads: ``ore`` (:func:`_in_slice`),
    ``geode`` (a vanilla ``minecraft:geode`` with Minecraft's placements) or
    ``patch`` (the plant patch family, nested features included); else None."""
    found = _in_slice(root, ident)
    if found is not None:
        return "ore", found, set(), set()
    found = _read_placed(root, ident)
    if found is None or not _vanilla_placements(found[2].get("placement", [])):
        return None
    kind = found[3].get("type")
    if kind == "minecraft:geode":
        return "geode", found, set(), set()
    nested: set[str] = set()
    coded: set[str] = set()
    if kind in ref.PATCH_TYPES | ref.SELECTOR_TYPES and _patch_files(root, found[3], nested, coded):
        return "patch", found, nested - {found[0], found[1]}, coded
    return None


def _int(value, what: str) -> int:
    if isinstance(value, dict) and value.get("type") == "minecraft:constant" and set(value) == {"type", "value"}:
        value = value["value"]  # a constant int provider, written out
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Refused(f"{what} is {json.dumps(value)}, not a constant whole number")
    return value


def _anchor(anchor, dimension: str) -> int:
    if not isinstance(anchor, dict) or len(anchor) != 1:
        raise _Refused(f"height anchor {json.dumps(anchor)} is not one of absolute/above_bottom/below_top")
    (kind, value), = anchor.items()
    value = _int(value, f"height anchor {kind}")
    if kind == "absolute":
        return value
    j_lo, j_hi = ref.JAVA_Y[dimension]
    b_lo, b_hi = ref.BEDROCK_Y[dimension]
    if kind == "above_bottom":
        if j_lo != b_lo:
            raise _Refused(f"above_bottom in the {dimension}: Java's bottom is y={j_lo}, Bedrock's y={b_lo}")
        return j_lo + value
    if kind == "below_top":
        if j_hi != b_hi:
            raise _Refused(f"below_top {value} in the {dimension}: Java's top is y={j_hi}, Bedrock's y={b_hi} "
                           "(#281 pick 4)")
        return j_hi - value
    raise _Refused(f"height anchor `{kind}` is not one of absolute/above_bottom/below_top")


_ANCHORS = {"absolute", "above_bottom", "below_top"}


def _height(height, dimension: str) -> dict:
    if not isinstance(height, dict):
        raise _Refused(f"height {json.dumps(height)} is not a height provider")
    if set(height) <= _ANCHORS and len(height) == 1:
        # A bare vertical anchor is a constant height (Java's HeightProvider
        # codec takes either form).
        return {"y": _anchor(height, dimension)}
    kind = height.get("type", "minecraft:constant")
    if kind == "minecraft:constant":
        return {"y": _anchor(height.get("value"), dimension)}
    lo = _anchor(height.get("min_inclusive"), dimension)
    hi = _anchor(height.get("max_inclusive"), dimension)
    if lo > hi:
        raise _Refused(f"height range {lo}..{hi} is empty")
    if kind == "minecraft:uniform":
        return {"y": {"distribution": "uniform", "extent": [lo, hi]}}
    if kind == "minecraft:trapezoid":
        plateau = height.get("plateau", 0)
        if plateau != 0:
            raise _Refused(f"a trapezoid height with plateau {plateau}: Bedrock's distributions have no "
                           "plateau (#281 pick 2)")
        return {"y": {"distribution": "triangle", "extent": [lo, hi]}}
    raise _Refused(f"height provider `{kind}` has no Bedrock distribution here")


def _distribution(pf: dict, dimension: str) -> dict:
    iterations = 1
    chance = None
    seen_count = False
    xz = 0
    y = None
    for p in _placements(pf):
        kind = p["type"]
        if kind == "minecraft:count":
            iterations *= _int(p.get("count"), "the count")
            seen_count = True
        elif kind == "minecraft:in_square":
            xz = {"distribution": "uniform", "extent": [0, 15]}
        elif kind == "minecraft:height_range":
            if y is not None:
                raise _Refused("two height_range placements")
            y = _height(p.get("height"), dimension)["y"]
        elif kind == "minecraft:rarity_filter":
            n = _int(p.get("chance"), "the rarity chance")
            if n < 1 or chance is not None:
                raise _Refused("a rarity filter Bedrock's single scatter chance can't express")
            chance = n
            if seen_count and iterations != 1:
                raise _Refused("a rarity filter after a count above 1: Java rolls it per vein, Bedrock's "
                               "scatter_chance once for all iterations")
        elif kind != "minecraft:biome":
            raise _Refused(f"placement `{kind}` has no Bedrock scatter parameter here")
    if y is None:
        raise _Refused("no height_range placement: the vein would sit at the chunk's origin height")
    if iterations < 1:
        raise _Refused(f"count {iterations}")
    dist = {"iterations": iterations}
    if chance is not None and chance > 1:
        dist["scatter_chance"] = {"numerator": 1, "denominator": chance}
    dist.update({"x": xz, "y": y, "z": xz})
    return dist


def _biomes(value) -> tuple[list[dict], str]:
    tags = _as_list(value)
    if not tags or not all(isinstance(t, str) and t.startswith("#") for t in tags):
        raise _Refused(f"biomes {json.dumps(value)[:80]}: only vanilla biome tags with a Bedrock biome tag map "
                       "(#281 pick 3)")
    filters, dims = [], set()
    for tag in tags:
        row = ref.BIOME_TAGS.get(tag[1:])
        if row is None:
            raise _Refused(f"biome tag `{tag}` has no Bedrock biome tag (#281 pick 3)")
        filters += row[0]
        dims.add(row[1])
    if len(dims) != 1:
        raise _Refused(f"biomes {json.dumps(value)} span dimensions {sorted(dims)}")
    if len(filters) > 1:
        filters = [{"any_of": filters}]
    return filters, dims.pop()


def _replace_rules(cf: dict, blocks: set[str]) -> tuple[list[dict], int, float]:
    config = cf.get("config")
    if not isinstance(config, dict):
        raise _Refused("the ore has no config")
    size = _int(config.get("size"), "the vein size")
    if size < 1:
        raise _Refused(f"vein size {size}")
    discard = config.get("discard_chance_on_air_exposure", 0.0)
    if not isinstance(discard, (int, float)) or isinstance(discard, bool) or not 0 <= discard <= 1:
        raise _Refused(f"discard_chance_on_air_exposure {json.dumps(discard)}")
    rules = []
    for target in _as_list(config.get("targets")):
        if not isinstance(target, dict):
            raise _Refused("an ore target is not an object")
        state = target.get("state") or {}
        name = state.get("Name") if isinstance(state, dict) else None
        if not isinstance(name, str):
            raise _Refused("an ore target has no state Name")
        if state.get("Properties"):
            raise _Refused(f"target `{name}` sets block-state properties {json.dumps(state['Properties'])}")
        if name not in blocks:
            raise _Refused(f"target block `{name}` isn't a block the pack ships")
        test = target.get("target") or {}
        kind = test.get("predicate_type") if isinstance(test, dict) else None
        if kind == "minecraft:block_match" and test.get("block") in ref.SAME_ID_BLOCKS:
            may = [test["block"]]
        elif kind == "minecraft:tag_match" and test.get("tag") in ref.BLOCK_TAGS:
            may = list(ref.BLOCK_TAGS[test["tag"]])
        else:
            raise _Refused(f"ore target test {json.dumps(test)[:80]} (only block_match of a vanilla block with the "
                           "same Bedrock id, or tag_match of a vanilla ore-replaceable tag)")
        rules.append({"places_block": name, "may_replace": may})
    if not rules:
        raise _Refused("the ore has no targets")
    return rules, size, float(discard)


def _int_range(value, what: str) -> tuple[int, int]:
    """A constant or ``minecraft:uniform`` int provider as (min, max)."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value, value
    if isinstance(value, dict) and value.get("type") == "minecraft:constant":
        v = _int(value.get("value"), what)
        return v, v
    if isinstance(value, dict) and value.get("type") == "minecraft:uniform":
        inner = value.get("value") if isinstance(value.get("value"), dict) else value
        lo = _int(inner.get("min_inclusive"), what)
        hi = _int(inner.get("max_inclusive"), what)
        if lo > hi:
            raise _Refused(f"{what} {lo}..{hi} is empty")
        return lo, hi
    raise _Refused(f"{what} is {json.dumps(value)[:80]}, not a constant or uniform whole number")


def _number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Refused(f"{what} is {json.dumps(value)}, not a number")
    return value


_GEODE_LAYERS = (("filling_provider", "filler"), ("inner_layer_provider", "inner_layer"),
                 ("alternate_inner_layer_provider", "alternate_inner_layer"),
                 ("middle_layer_provider", "middle_layer"), ("outer_layer_provider", "outer_layer"))


def _geode_block(name, blocks: set[str], what: str) -> str:
    if not isinstance(name, str):
        raise _Refused(f"{what} names no block")
    if name not in blocks and name not in ref.GEODE_VANILLA_BLOCKS:
        raise _Refused(f"{what} `{name}` isn't a block the pack ships or a vanilla block with the same "
                       "Bedrock id")
    return name


def _geode(cf: dict, blocks: set[str]) -> tuple[dict, list[str]]:
    """The Bedrock ``minecraft:geode_feature`` body for a Java geode, and the
    Java fields it can't carry (pick 1) with their values, for the notes.

    Mapping (Java: minecraft.wiki "Amethyst Geode" oldid 3811952, Config;
    Bedrock: bedrock-samples documentation/Features.html and
    MicrosoftDocs/minecraft-creator Features/minecraftGeode_feature.md):
    the five ``*_provider`` blocks -> ``filler``, ``inner_layer``,
    ``alternate_inner_layer``, ``middle_layer``, ``outer_layer``;
    ``inner_placements`` -> ``inner_placements`` (block names, pick 2);
    ``outer_wall_distance``, ``distribution_points``, ``point_offset`` (int
    providers) -> ``min_``/``max_`` of the same name; ``crack.*``,
    ``noise_multiplier``, ``use_potential_placements_chance``,
    ``use_alternate_layer0_chance``, ``placements_require_layer0_alternate``
    and ``invalid_blocks_threshold`` -> the fields of the same name;
    ``min_gen_offset``/``max_gen_offset`` -m/m -> ``max_radius`` m (pick 1).
    Every field must be written in the jar: a Java default is never assumed."""
    config = cf.get("config")
    if not isinstance(config, dict):
        raise _Refused("the geode has no config")
    need = {"blocks", "layers", "crack", "noise_multiplier", "use_potential_placements_chance",
            "use_alternate_layer0_chance", "placements_require_layer0_alternate", "outer_wall_distance",
            "distribution_points", "point_offset", "min_gen_offset", "max_gen_offset", "invalid_blocks_threshold"}
    missing = sorted(need - set(config))
    if missing:
        raise _Refused(f"the geode leaves {', '.join(missing)} to Java's defaults, which aren't read here")
    blk = config["blocks"]
    if not isinstance(blk, dict):
        raise _Refused("the geode's blocks are not an object")
    body: dict = {}
    for java, bedrock in _GEODE_LAYERS:
        provider = blk.get(java)
        if not isinstance(provider, dict) or provider.get("type") != "minecraft:simple_state_provider":
            raise _Refused(f"{java} {json.dumps(provider)[:80]} is not a simple_state_provider (one block)")
        state = provider.get("state")
        if not isinstance(state, dict) or state.get("Properties"):
            raise _Refused(f"{java} sets block-state properties {json.dumps(state)[:80]}")
        body[bedrock] = _geode_block(state.get("Name"), blocks, java)
    placements = blk.get("inner_placements")
    if not isinstance(placements, list) or not placements:
        raise _Refused("the geode has no inner_placements")
    names = []
    for state in placements:
        if not isinstance(state, dict):
            raise _Refused("an inner placement is not a block state")
        props = state.get("Properties") or {}
        # Java's GeodeFeature.place sets FACING to the side it places on and
        # WATERLOGGED from the fluid there (1.20.1 client jar, class dku, read
        # through Mojang's client mappings), so those two are not the data's.
        other = sorted(set(props) - {"facing", "waterlogged"}) if isinstance(props, dict) else ["?"]
        if other:
            raise _Refused(f"inner placement `{state.get('Name')}` sets block-state properties {other}")
        names.append(_geode_block(state.get("Name"), blocks, "inner placement"))
    body["inner_placements"] = names
    for java in ("outer_wall_distance", "distribution_points", "point_offset"):
        lo, hi = _int_range(config[java], java)
        body[f"min_{java}"], body[f"max_{java}"] = lo, hi
    lo, hi = _int(config["min_gen_offset"], "min_gen_offset"), _int(config["max_gen_offset"], "max_gen_offset")
    if lo != -hi or hi < 1:
        raise _Refused(f"gen offsets {lo}..{hi} are not one radius about the start, which Bedrock's single "
                       "max_radius can't express")
    body["max_radius"] = hi
    crack = config["crack"]
    if not isinstance(crack, dict) or set(crack) != {"generate_crack_chance", "base_crack_size",
                                                      "crack_point_offset"}:
        raise _Refused(f"the geode's crack {json.dumps(crack)[:80]} doesn't name its three fields")
    body["crack_point_offset"] = _int(crack["crack_point_offset"], "crack_point_offset")
    body["generate_crack_chance"] = _number(crack["generate_crack_chance"], "generate_crack_chance")
    body["base_crack_size"] = _number(crack["base_crack_size"], "base_crack_size")
    body["noise_multiplier"] = _number(config["noise_multiplier"], "noise_multiplier")
    for name in ("use_potential_placements_chance", "use_alternate_layer0_chance"):
        body[name] = _number(config[name], name)
    flag = config["placements_require_layer0_alternate"]
    if not isinstance(flag, bool):
        raise _Refused(f"placements_require_layer0_alternate is {json.dumps(flag)}")
    body["placements_require_layer0_alternate"] = flag
    body["invalid_blocks_threshold"] = _int(config["invalid_blocks_threshold"], "invalid_blocks_threshold")
    for name, (a, b) in ref.GEODE_RANGES.items():
        if not a <= body[name] <= b:
            raise _Refused(f"{name} {body[name]} is outside Bedrock's range {a}..{b}")
    for a, b in (("min_outer_wall_distance", "max_outer_wall_distance"),
                 ("min_distribution_points", "max_distribution_points"), ("min_point_offset", "max_point_offset")):
        if body[a] > body[b]:
            raise _Refused(f"{a} {body[a]} is above {b} {body[b]}")
    layers = config["layers"]
    if not isinstance(layers, dict):
        raise _Refused("the geode's layers are not an object")
    dropped = [f"layers {json.dumps(layers, sort_keys=True)} (Bedrock has no layer thickness field; Java's defaults "
               f"are {json.dumps(ref.JAVA_GEODE_DEFAULTS['layers'], sort_keys=True)})",
               f"min_gen_offset/max_gen_offset {lo}/{hi}, a Chebyshev cutoff about the start, written as "
               f"max_radius {hi}"]
    for name in ("cannot_replace", "invalid_blocks"):
        if blk.get(name) is not None:
            dropped.append(f"{name} {json.dumps(blk.get(name))} (Bedrock has no such field)")
    if any(isinstance(st.get("Properties"), dict) and "facing" in st["Properties"] for st in placements):
        dropped.append("the inner placements' facing, which Java turns to the side each one grows on; Bedrock "
                       "places the named blocks in their default state (pick 2)")
    return body, dropped


def _shipped_blocks(files: dict) -> set[str]:
    out = set()
    for path, body in files.items():
        if path.startswith("blocks/") and isinstance(body, dict):
            ident = ((body.get("minecraft:block") or {}).get("description") or {}).get("identifier")
            if isinstance(ident, str):
                out.add(ident)
    return out


def _file_name(ident: str, taken: set[str], suffix: str = "") -> str:
    ns, path = _split(ident)
    base = re.sub(r"[^a-z0-9_]", "_", path.lower()) + suffix
    name = base if base not in taken else f"{ns}_{base}"
    taken.add(name)
    return name


def convert(root: Path, files: dict, namespaces: set[str], code: list | None = None) -> FeatureResult:
    """Ore and geode features the jar's Forge/NeoForge biome modifiers add,
    converted, and its plant patches filed as residue with the reason; and
    the same for those its Fabric code adds (``code``:
    :class:`portkit.biomecode.CodeAttachment` rows, read from the bytecode),
    each shaped like a modifier."""
    root = Path(root)
    out = FeatureResult()
    blocks = _shipped_blocks(files)
    data = root / "data"
    modifiers: list[tuple[str, dict]] = []
    for path in sorted(data.glob("*/*/biome_modifier/**/*.json")) if data.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        if _MODIFIER.match(rel) and _MODIFIER.match(rel).group(1) in namespaces:
            doc = _read(path)
            if isinstance(doc, dict):
                modifiers.append((rel, doc))
    removed: dict[str, str] = {}
    for rel, doc in modifiers:
        if doc.get("type") in _REMOVE:
            for f in _as_list(doc.get("features")):
                if isinstance(f, str):
                    removed[f] = rel
    code = list(code or [])
    for c in code:
        if c.removal:
            removed[c.feature] = c.source

    feature_names: dict[str, str] = {}  # configured rel -> feature id written
    taken_features: set[str] = set()
    taken_rules: set[str] = set()
    adds_per_pf: dict[str, int] = {}
    plans = []
    for rel, doc in modifiers:
        if doc.get("type") not in _ADD:
            continue
        feats = _as_list(doc.get("features"))
        found = [_classify(root, f) for f in feats]
        if not feats or any(x is None for x in found):
            continue  # not wholly ores, geodes and patches: left for the other passes
        plans.append((rel, doc, list(zip(feats, found)), None))
        for f in feats:
            adds_per_pf[f] = adds_per_pf.get(f, 0) + 1
    for c in code:
        if c.removal:
            continue
        found = _classify(root, c.feature)
        if found is None:
            continue  # not a feature this module reads: left for the other passes
        plans.append((c.source, c.doc, [(c.feature, found)], c))
        adds_per_pf[c.feature] = adds_per_pf.get(c.feature, 0) + 1
    # A remove modifier naming only features read here is residue of its own:
    # the Bedrock rule can't subtract the biomes it names (pick 6).
    removals = []
    for rel, doc in modifiers:
        feats = _as_list(doc.get("features"))
        if doc.get("type") in _REMOVE and feats and all(_classify(root, f) is not None for f in feats):
            removals.append(rel)

    converted_cf: set[str] = set()
    refused: dict[str, tuple[str, str, set[str], str]] = {}  # placed rel -> (reason, configured rel, nested, kind)
    empty_modifiers: list[str] = []
    for rel, doc, entries, from_code in plans:
        if from_code is None:
            out.consumed.add(rel)
            mod_name = _MODIFIER.match(rel).group(3)
        else:
            mod_name = re.sub(r"[^a-z0-9_]", "_", from_code.source.split(" ")[0].rsplit(".", 1)[-1].lower())
        rules_before = len(out.files)
        for ident, (kind, (prel, crel, pf, cf), nested, coded) in entries:
            out.consumed |= {prel, crel} | nested
            approximated: list[str] = []
            try:
                if ident in removed:
                    raise _Refused(f"`{removed[ident]}` removes it from some biomes, which a Bedrock feature rule "
                                   "can't subtract (#281 pick 6)")
                if from_code is not None and from_code.refused:
                    raise _Refused(f"attached in code by {from_code.source}: {from_code.refused}")
                step = doc.get("step")
                if kind == "patch" and coded:
                    raise _Refused(f"it places features through the mod's own types ({', '.join(sorted(coded))}), "
                                   "which are its code")
                if kind == "patch":
                    _biomes(doc.get("biomes"))
                    raise _Refused(f"a plant patch (`{cf.get('type')}`): Java scatters `tries` placements with "
                                   "xz_spread/y_spread offsets and per-block conditions, which no corpus mod's "
                                   "patch has reached a Bedrock mapping for yet (#281 slice 3 pick 5)")
                passname = (ref.GEODE_STEPS if kind == "geode" else ref.STEPS).get(step)
                if passname is None:
                    raise _Refused(f"generation step `{step}` isn't one this slice maps for a {kind} "
                                   f"({', '.join(ref.GEODE_STEPS if kind == 'geode' else ref.STEPS)})")
                biome_filter, dimension = _biomes(doc.get("biomes"))
                if kind == "geode":
                    body, approximated = _geode(cf, blocks)
                    rules = None
                else:
                    rules, size, discard = _replace_rules(cf, blocks)
                dist = _distribution(pf, dimension)
                y = dist["y"]
                lo, hi = (y, y) if isinstance(y, int) else y["extent"]
                b_lo, b_hi = ref.BEDROCK_Y[dimension]
                if lo < b_lo or hi > b_hi:
                    raise _Refused(f"heights {lo}..{hi} reach outside Bedrock's {dimension} ({b_lo}..{b_hi})")
            except _Refused as why:
                refused[prel] = (str(why), crel, nested, kind)
                continue
            if crel not in feature_names:
                fname = _file_name(pf["feature"], taken_features)
                feature_id = f"{_split(pf['feature'])[0]}:{fname}"
                feature_names[crel] = feature_id
                if kind == "geode":
                    out.files[f"features/{fname}.json"] = {
                        "format_version": FEATURE_FORMAT,
                        "minecraft:geode_feature": {"description": {"identifier": feature_id}, **body}}
                    out.notes.append(f"approximated geode (#281 pick 1): `{pf['feature']}` written as Bedrock's "
                                     "minecraft:geode_feature without " + "; ".join(approximated) + ".")
                else:
                    body = {"description": {"identifier": feature_id}, "count": size, "replace_rules": rules}
                    if discard:
                        body["discard_chance_on_air_exposure"] = discard
                    out.files[f"features/{fname}.json"] = {"format_version": FEATURE_FORMAT,
                                                           "minecraft:ore_feature": body}
            converted_cf.add(crel)
            if from_code is not None:
                out.consumed |= from_code.consumed
                out.notes.append(f"{kind.capitalize()} `{ident}`: attached to biomes {', '.join(doc['biomes'])} at "
                                 f"{doc['step']} by {from_code.source}.")
            suffix = "_feature_rules" if adds_per_pf.get(ident, 0) <= 1 else f"__{mod_name}_feature_rules"
            rname = _file_name(ident, taken_rules, suffix)
            rule_id = f"{_split(ident)[0]}:{rname}"
            out.files[f"feature_rules/{rname}.json"] = {
                "format_version": RULE_FORMAT,
                "minecraft:feature_rules": {
                    "description": {"identifier": rule_id, "places_feature": feature_names[crel]},
                    "conditions": {"placement_pass": passname, "minecraft:biome_filter": biome_filter},
                    "distribution": dist,
                },
            }
            if kind == "geode":
                out.geodes.append({"rule": rule_id, "feature": feature_names[crel], "dimension": dimension,
                                   "y": [lo, hi]})
                if step == "local_modifications":
                    out.notes.append(f"Geode `{ident}`: Java's local_modifications step written as Bedrock's "
                                     "before_underground_pass, the pass before the ores' (#281 slice 3 pick 3).")
            else:
                out.ores.append({"rule": rule_id, "feature": feature_names[crel], "dimension": dimension,
                                 "blocks": [r["places_block"] for r in rules],
                                 "replaces": [r["may_replace"][0] for r in rules],
                                 "y": [lo, hi]})
            if pf.get("placement") and any(p["type"] == "minecraft:height_range"
                                           and (p.get("height") or {}).get("type") == "minecraft:trapezoid"
                                           for p in _placements(pf)):
                out.notes.append(f"{kind.capitalize()} `{ident}`: Java's trapezoid height range written as Bedrock's "
                                 f"triangle distribution over {lo}..{hi} (#281 pick 2).")
        if len(out.files) == rules_before and from_code is None:
            empty_modifiers.append(rel)
    # Each file counted once, even when several placed features refuse it.
    counted: set[str] = set()
    for prel, (reason, crel, nested, kind) in sorted(refused.items()):
        group = [crel] if crel not in converted_cf else []
        group += sorted(nested - converted_cf)
        count = 1 + sum(1 for r in group if r not in counted and r != prel)
        counted |= set(group) | {prel}
        what = {"ore": "ore placed feature (and its configured feature)",
                "geode": "geode placed feature (and its configured feature)",
                "patch": "plant patch placed feature (with the features it places)"}[kind]
        out.unhandled.append(Unhandled(source=prel, kind=KIND, count=count,
                                       reason=f"{what} not converted: {reason}"))
    for rel in empty_modifiers:
        out.unhandled.append(Unhandled(source=rel, kind=KIND, count=1,
                                       reason="biome modifier adding only features that didn't convert (their "
                                              "placed features are residue of their own)"))
    for rel in removals:
        out.consumed.add(rel)
        out.unhandled.append(Unhandled(source=rel, kind=KIND, count=1,
                                       reason="biome modifier removing features from biomes, which a Bedrock "
                                              "feature rule can't subtract (#281 pick 6)"))
    return out
