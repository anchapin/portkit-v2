"""Alloy Forgery forges (#171): precise residue until a scripted forge exists.

Alloy Forgery (wisp-forest/alloy-forgery) is a separate mod that other mods
add forge recipes, forges and fuels to as data. Its forge is Java code: a
controller block Alloy Forgery registers for each forge definition, a
multiblock of the forge's material around it, a fuel store, tiers and a
ticking 10-slot inventory. Nothing of that is in a recipe mod's jar, and a
Bedrock custom block has no ticking inventory or fuel store, so there is no
Bedrock forge to run any of it, and a crafting-table or furnace stand-in
would drop the tier gate, the fuel and the tier bonus (docs/decisions.md,
2026-10-12 and 2026-10-15).

What this module does is say exactly what each file sets, read from the
file, so the residue carries the forge's rules for later work instead of
"unsupported":

- :func:`forging_reason` is the reason for one ``alloy_forgery:forging``
  recipe (``machine_recipe`` residue, written by :mod:`.recipes`): inputs,
  output, minimum forge tier, fuel per tick, tier overrides.
- :func:`convert` claims the forge data Alloy Forgery reads from other mods
  as ``machine_data`` residue: forge definitions (``alloy_forges/`` from
  before 2.5, ``alloy_forge/forge/`` since), forge tiers and tier bindings,
  forge fuels, and Alloy Forgery's two recipe tags that only steer its own
  copying of blast-furnace recipes.

Sources, cited by line in the reasons and the decisions entry:
Alloy Forgery 2.5.0 = branch ``1.21.1`` @48e309f7e3f23c5ce98e87821107698581fe726f,
Alloy Forgery 2.4.1 = tag ``2.4.1+1.21`` @ed938ab4631368fa67217617839c79b3b3998b8a
(Mythic Metals 0.24.6 requires ``alloy_forgery >=2.4.1``), owo-lib ``1.21``
``ModDataLoader``.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..model import ConversionResult, SourceMod, Unhandled

FORGING = "alloy_forgery:forging"

# Data a Java machine reads at runtime (forge definitions, tiers, fuels, the
# forge's recipe tags). There is no Bedrock machine to read it until a
# scripted forge exists (#171), so the residue agent skips the kind
# (agent/residue.py SKIP_KINDS).
MACHINE_DATA = "machine_data"

_AF = "wisp-forest/alloy-forgery"
_AF_250 = f"{_AF} 2.5.0 @48e309f"
_AF_241 = f"{_AF} 2.4.1 @ed938ab"

# What Bedrock lacks, said once at the end of every reason.
_NO_BEDROCK_FORGE = (
    "Alloy Forgery is a separate mod whose jar isn't converted with this one, and a Bedrock custom "
    "block has no ticking inventory or fuel store, so there is no Bedrock forge to run it (that needs "
    "a scripted forge, #171); a crafting-table or furnace stand-in would drop the tier gate, the fuel "
    "and the tier bonus"
)

# The same for a data file: what it sets has nothing on Bedrock to read it.
_NO_BEDROCK_FORGE_DATA = (
    "Alloy Forgery is a separate mod whose jar isn't converted with this one, and a Bedrock custom "
    "block has no ticking inventory or fuel store, so there is no Bedrock forge to read this (that "
    "needs a scripted forge, #171)"
)

# Subdirectories of data/<namespace>/ that Alloy Forgery reads.
_OLD_FORGES = "alloy_forges"  # ForgeDefinition#initLoaders L112-117 (2.5.0), the 2.4.1 format
_FORGES = ("alloy_forge", "forge")  # ForgeDefinition#initLoaders L119-124 (2.5.0)
_TIERS = ("alloy_forge", "tier")  # ForgeTierDataLoader L22-29
_BINDINGS = ("alloy_forge", "tier_binding")  # ForgeTierDataLoader L31-36
_FUELS = "alloy_forge_fuels"  # ForgeFuelDataLoader L154-159

# Alloy Forgery's recipe tags (BlastFurnaceRecipeAdapter L32, L37), read only
# while it copies blasting recipes into its forges (#addRecipes L47-71).
_RECIPE_TAGS = {
    "blacklisted_blasting_recipes": (
        "the blasting recipes it lists are not copied into Alloy Forgery's forges "
        f"(BlastFurnaceRecipeAdapter#addRecipes L50, {_AF_250})"
    ),
    "blacklisted_increased_blasting_outputs": (
        "the blasting recipes it lists get no larger output at tier 3 and up when Alloy Forgery copies them into "
        f"its forges (BlastFurnaceRecipeAdapter#addRecipes L66-71, {_AF_250})"
    ),
}
# Alloy Forgery's RecipeTagLoader reads "tags/recipe" (L29, the same in 2.4.1).
_TAG_DIR = "recipe"


def _read(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _ingredient(entry) -> str | None:
    """One counted input as ``N x item`` or ``N x #tag`` (CountedIngredient:
    ``count`` defaults to 1)."""
    if not isinstance(entry, dict):
        return None
    count = entry.get("count", 1)
    if _int(count) is None or count < 1:
        return None
    if isinstance(entry.get("item"), str):
        what = entry["item"]
    elif isinstance(entry.get("tag"), str):
        what = "#" + entry["tag"]
    else:
        return None
    return f"{count} x {what}"


def _stack(spec) -> str | None:
    """An output or override as ``N item`` (OutputData: ``id`` or ``item``
    with ``count``), ``N`` for a count-only override, else None."""
    if not isinstance(spec, dict) or _int(spec.get("count")) is None:
        return None
    item = spec.get("id", spec.get("item"))
    if item is None:
        return str(spec["count"])
    if not isinstance(item, str):
        return None
    return f"{spec['count']} {item}"


def _range(key: str) -> str | None:
    """An override key as AlloyForgeRecipe$OverrideRange#fromString reads it
    (``"3+"``, ``"1 to 3"``, ``"2"``)."""
    k = key.strip()
    if k.endswith("+") and k[:-1].isdigit():
        return f"tier {k[:-1]} and up"
    parts = k.split(" to ")
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        return f"tiers {parts[0]} to {parts[1]}"
    if k.isdigit():
        return f"tier {k}"
    return None


def forging_reason(recipe: dict, forges: list[str] | None = None) -> str:
    """Why one ``alloy_forgery:forging`` recipe stays residue, with what it does.

    ``forges`` names the forge definitions the recipe's own jar ships (see
    :func:`forge_names`). A recipe whose fields aren't the shape Alloy
    Forgery reads gets the general reason without the parts it couldn't read.
    """
    head = "an Alloy Forgery forge recipe"
    facts: list[str] = []  # verb phrases, each read from one field
    inputs = recipe.get("inputs")
    if isinstance(inputs, list) and inputs:
        read = [_ingredient(e) for e in inputs]
        if all(read):
            shown = ", ".join(read) if len(read) <= 5 else f"{len(read)} different inputs"
            output = _stack(recipe.get("output"))
            into = f" into {output}" if output else ""
            facts.append(f"forges {shown}{into}")
    tier = _int(recipe.get("min_forge_tier"))
    fuel = _int(recipe.get("fuel_per_tick"))
    if tier is not None:
        facts.append(f"needs a forge of tier {tier} or higher (ForgeControllerBlockEntity#canSmelt L317)")
    if fuel is not None:
        facts.append(
            f"burns {fuel} fuel per tick times the forge tier's speed multiplier for the tier's smelt "
            "time (ForgeControllerBlockEntity#tick L279-288)"
        )
    overrides = recipe.get("overrides")
    if isinstance(overrides, dict) and overrides:
        said = []
        for key, spec in overrides.items():
            where, what = _range(key) if isinstance(key, str) else None, _stack(spec)
            if where is None or what is None:
                said = []
                break
            said.append(f"{what} at {where}")
        if said:
            facts.append("makes " + " and ".join(said) + " instead (AlloyForgeRecipe#getResult)")
    if len(facts) > 1:
        facts[-1] = "and " + facts[-1]
    body = head + (": it " + ", ".join(facts) if facts else "")
    station = (
        "the forge is a multiblock of a forge definition's material around a controller block "
        "alloy_forgery:<material>_forge_controller that Alloy Forgery's code registers from the "
        "definition (ForgeRegistry#registerDefinition L40-50, ForgeControllerBlockEntity#verifyMultiblock "
        f"L420-430, {_AF_250})"
    )
    if forges:
        station += "; this jar defines " + ", ".join(forges) + " (its own residue says more)"
    return "; ".join((body, station, _NO_BEDROCK_FORGE))


def _reads_forges(mod: SourceMod) -> bool:
    """Whether Alloy Forgery reads this namespace's forge definitions.

    owo-lib's ModDataLoader#load (``1.21``) reads ``data/<mod id>/<subdir>``
    of each loaded mod under that mod's own id only, so a forge definition in
    another namespace of the jar is never loaded. Without metadata the mod
    ids are unknown and the definitions are taken as read.
    """
    return mod.mods is None or mod.namespace in mod.mods


def _forge_files(mod: SourceMod) -> list[tuple[Path, bool]]:
    """(file, old format) for every forge definition under this namespace."""
    found = []
    for folder, old in ((mod.data / _OLD_FORGES, True), (mod.data.joinpath(*_FORGES), False)):
        if folder.is_dir():
            found += [(p, old) for p in sorted(folder.rglob("*.json"))]
    return found


def _forge_id(mod: SourceMod, path: Path, old: bool) -> str:
    folder = mod.data / _OLD_FORGES if old else mod.data.joinpath(*_FORGES)
    return f"{mod.namespace}:{path.relative_to(folder).with_suffix('').as_posix()}"


def _controller(material) -> str | None:
    """The controller block id ForgeRegistry#registerDefinition L42 gives a
    forge: ``alloy_forgery:<material path>_forge_controller``."""
    if not isinstance(material, str) or not material:
        return None
    return f"alloy_forgery:{material.split(':', 1)[-1]}_forge_controller"


def forge_names(mod: SourceMod) -> list[str]:
    """The forges this namespace defines that Alloy Forgery loads, as
    ``<forge id>, controller <block>``, for :func:`forging_reason`."""
    if not _reads_forges(mod):
        return []
    names = []
    for path, old in _forge_files(mod):
        body = _read(path)
        controller = _controller(body.get("material")) if isinstance(body, dict) else None
        ident = _forge_id(mod, path, old)
        names.append(f"{ident}, controller {controller}" if controller else ident)
    return names


def _forge_reason(mod: SourceMod, path: Path, old: bool) -> str:
    ident = _forge_id(mod, path, old)
    if not _reads_forges(mod):
        return (
            f"an Alloy Forgery forge definition ({ident}) that Java never loads: owo-lib's "
            "ModDataLoader#load reads forge definitions only from data/<mod id>/ of each mod, and "
            f"{mod.namespace!r} is not a mod id this jar declares; nothing to convert"
        )
    body = _read(path)
    if not isinstance(body, dict):
        return f"an Alloy Forgery forge definition ({ident}) that isn't a JSON object; {_NO_BEDROCK_FORGE_DATA}"
    controller = _controller(body.get("material"))
    material = body.get("material") if controller else None
    extra = body.get("additional_materials")
    extra = [m for m in extra if isinstance(m, str)] if isinstance(extra, list) else []
    parts = [f"an Alloy Forgery forge definition ({ident})"]
    if controller:
        built = f"a multiblock of {material}" + (f" (or {', '.join(extra)})" if extra else "")
        parts.append(
            f"Alloy Forgery registers the controller block and item {controller} for it, and the forge "
            f"is {built} around that controller (ForgeRegistry#registerDefinition L40-50, "
            f"ForgeControllerBlockEntity#verifyMultiblock L420-430, {_AF_250})"
        )
    if old:
        tier, speed, capacity = (body.get(k) for k in ("tier", "speed_multiplier", "fuel_capacity"))
        if _int(tier) is not None:
            speed = speed if isinstance(speed, (int, float)) and not isinstance(speed, bool) else 1
            capacity = _int(capacity) if _int(capacity) is not None else 48000
            parts.append(
                f"in the pre-2.5 format: Alloy Forgery 2.4.1 runs it at tier {tier}, speed multiplier "
                f"{speed} and fuel capacity {capacity} (ForgeDefinition#loadAndEnqueue L68-88, read from "
                f"alloy_forges by ForgeRegistry$Loader L87, {_AF_241}), "
                "but 2.5.0 still loads the folder and drops those three fields, so the forge runs at the "
                "tier a tier_binding gives it, else ForgeTier.DEFAULT (tier 1, speed 1, capacity 48000) "
                f"(ForgeDefinition#loadAndEnqueue L44-58, ForgeControllerBlockEntity#forgeTier L88-94, "
                f"{_AF_250}); which applies depends on the Alloy Forgery version installed"
            )
        else:
            parts.append(
                "in the pre-2.5 format, but without the integer `tier` that format requires "
                f"(ForgeDefinition#loadAndEnqueue L45, {_AF_250})"
            )
    else:
        parts.append(f"its tier comes from a tier_binding (ForgeTierDataLoader L31-36, {_AF_250})")
    parts.append(_NO_BEDROCK_FORGE_DATA)
    return "; ".join(parts)


def _fuel_reason(path: Path) -> str:
    body = _read(path)
    fuels = body.get("fuels") if isinstance(body, dict) else None
    said = []
    if isinstance(fuels, list):
        for entry in fuels:
            if not (isinstance(entry, dict) and isinstance(entry.get("item"), str)
                    and _int(entry.get("fuel")) is not None):
                said = []
                break
            back = entry.get("return_item")
            said.append(f"{entry['item']} {entry['fuel']}"
                        + (f" (gives back {back})" if isinstance(back, str) else ""))
    listed = (": " + ", ".join(said)) if said else ""
    return (
        f"Alloy Forgery forge fuels{listed}; an item in a forge controller's fuel slot is used up for "
        "that much fuel while the forge's fuel capacity has room (ForgeFuelDataLoader L154-159, "
        f"ForgeControllerBlockEntity#tick L204-215, {_AF_250}); {_NO_BEDROCK_FORGE_DATA}"
    )


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    data = mod.data
    if not data.is_dir():
        return result
    for path, old in _forge_files(mod):
        rel = result.claim(mod, path)
        result.unhandled.append(Unhandled(rel, MACHINE_DATA, _forge_reason(mod, path, old)))
    for parts, what in ((_TIERS, "forge tier"), (_BINDINGS, "forge tier binding")):
        folder = data.joinpath(*parts)
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.json")):
            rel = result.claim(mod, path)
            reason = (
                f"an Alloy Forgery {what} (tier, speed multiplier, fuel capacity and smelt time a forge "
                f"runs at; ForgeTierDataLoader L22-36, ForgeTier, {_AF_250}); {_NO_BEDROCK_FORGE_DATA}"
            )
            result.unhandled.append(Unhandled(rel, MACHINE_DATA, reason))
    fuels = data / _FUELS
    if fuels.is_dir():
        for path in sorted(fuels.rglob("*.json")):
            rel = result.claim(mod, path)
            result.unhandled.append(Unhandled(rel, MACHINE_DATA, _fuel_reason(path)))
    if mod.namespace == "alloy_forgery":
        for name, effect in _RECIPE_TAGS.items():
            path = data / "tags" / _TAG_DIR / f"{name}.json"
            if not path.is_file():
                continue
            rel = result.claim(mod, path)
            body = _read(path)
            values = body.get("values") if isinstance(body, dict) else None
            count = f" ({len(values)} recipes)" if isinstance(values, list) else ""
            reason = (
                f"Alloy Forgery's recipe tag alloy_forgery:{name}{count}: {effect}; vanilla blast "
                "furnaces still run those recipes, which convert (or not) as ordinary blasting recipes "
                "on their own, so on Bedrock, which has no Alloy Forgery forge, the tag has nothing to "
                "change"
            )
            result.unhandled.append(Unhandled(rel, MACHINE_DATA, reason))
    return result
