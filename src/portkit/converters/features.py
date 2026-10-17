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
    if not isinstance(ident, str):
        return None
    ns, path = _split(ident)
    prel = f"data/{ns}/worldgen/placed_feature/{path}.json"
    pf = _read(root / prel)
    if not isinstance(pf, dict) or not isinstance(pf.get("feature"), str):
        return None
    if any(p.get("type") not in _VANILLA_PLACEMENTS for p in _placements(pf)):
        return None
    cns, cpath = _split(pf["feature"])
    crel = f"data/{cns}/worldgen/configured_feature/{cpath}.json"
    cf = _read(root / crel)
    if not isinstance(cf, dict) or cf.get("type") != "minecraft:ore":
        return None
    return prel, crel, pf, cf


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
    """Ore features the jar's Forge/NeoForge biome modifiers add, converted;
    and those its Fabric code adds (``code``: :class:`portkit.biomecode.CodeAttachment`
    rows, read from the bytecode), each shaped like a modifier."""
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
        found = [_in_slice(root, f) for f in feats]
        if not feats or any(x is None for x in found):
            continue  # not wholly ores: left for the other passes
        plans.append((rel, doc, list(zip(feats, found)), None))
        for f in feats:
            adds_per_pf[f] = adds_per_pf.get(f, 0) + 1
    for k, c in enumerate(code):
        if c.removal:
            continue
        found = _in_slice(root, c.feature)
        if found is None:
            continue  # not a vanilla ore with vanilla placements: left for the other passes
        plans.append((c.source, c.doc, [(c.feature, found)], c))
        adds_per_pf[c.feature] = adds_per_pf.get(c.feature, 0) + 1

    converted_cf: set[str] = set()
    refused: dict[str, tuple[str, str]] = {}  # placed rel -> (reason, configured rel)
    empty_modifiers: list[str] = []
    for rel, doc, entries, from_code in plans:
        if from_code is None:
            out.consumed.add(rel)
            mod_name = _MODIFIER.match(rel).group(3)
        else:
            mod_name = re.sub(r"[^a-z0-9_]", "_", from_code.source.split(" ")[0].rsplit(".", 1)[-1].lower())
        rules_before = len(out.ores)
        for ident, (prel, crel, pf, cf) in entries:
            out.consumed |= {prel, crel}
            try:
                if ident in removed:
                    raise _Refused(f"`{removed[ident]}` removes it from some biomes, which a Bedrock feature rule "
                                   "can't subtract (#281 pick 6)")
                if from_code is not None and from_code.refused:
                    raise _Refused(f"attached in code by {from_code.source}: {from_code.refused}")
                step = doc.get("step")
                passname = ref.STEPS.get(step)
                if passname is None:
                    raise _Refused(f"generation step `{step}` isn't an ore step (underground_ores, "
                                   "underground_decoration)")
                biome_filter, dimension = _biomes(doc.get("biomes"))
                rules, size, discard = _replace_rules(cf, blocks)
                dist = _distribution(pf, dimension)
                y = dist["y"]
                lo, hi = (y, y) if isinstance(y, int) else y["extent"]
                b_lo, b_hi = ref.BEDROCK_Y[dimension]
                if lo < b_lo or hi > b_hi:
                    raise _Refused(f"heights {lo}..{hi} reach outside Bedrock's {dimension} ({b_lo}..{b_hi})")
            except _Refused as why:
                refused[prel] = (str(why), crel)
                continue
            if crel not in feature_names:
                fname = _file_name(pf["feature"], taken_features)
                feature_id = f"{_split(pf['feature'])[0]}:{fname}"
                feature_names[crel] = feature_id
                body = {"description": {"identifier": feature_id}, "count": size, "replace_rules": rules}
                if discard:
                    body["discard_chance_on_air_exposure"] = discard
                out.files[f"features/{fname}.json"] = {"format_version": FEATURE_FORMAT,
                                                       "minecraft:ore_feature": body}
            converted_cf.add(crel)
            if from_code is not None:
                out.consumed |= from_code.consumed
                out.notes.append(f"Ore `{ident}`: attached to biomes {', '.join(doc['biomes'])} at "
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
            out.ores.append({"rule": rule_id, "feature": feature_names[crel], "dimension": dimension,
                             "blocks": [r["places_block"] for r in rules],
                             "replaces": [r["may_replace"][0] for r in rules],
                             "y": [lo, hi]})
            if pf.get("placement") and any(p["type"] == "minecraft:height_range"
                                           and (p.get("height") or {}).get("type") == "minecraft:trapezoid"
                                           for p in _placements(pf)):
                out.notes.append(f"Ore `{ident}`: Java's trapezoid height range written as Bedrock's triangle "
                                 f"distribution over {lo}..{hi} (#281 pick 2).")
        if len(out.ores) == rules_before and from_code is None:
            empty_modifiers.append(rel)
    for prel, (reason, crel) in sorted(refused.items()):
        count = 1 + (crel not in converted_cf)
        out.unhandled.append(Unhandled(source=prel, kind=KIND, count=count,
                                       reason=f"ore placed feature (and its configured feature) not converted: "
                                              f"{reason}"))
    # Each configured feature counted once even when several placed features refuse it.
    seen: set[str] = set()
    for u in out.unhandled:
        crel = refused[u.source][1]
        if u.count == 2 and crel in seen:
            u.count = 1
        seen.add(crel)
    for rel in empty_modifiers:
        out.unhandled.append(Unhandled(source=rel, kind=KIND, count=1,
                                       reason="biome modifier adding only ores that didn't convert (their "
                                              "placed features are residue of their own)"))
    return out
