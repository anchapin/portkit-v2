"""Named variations: one block per variant a mod's code registers (#296).

Some mods ship one blockstate per block family with one bare variant per
variation and register the variations from code (an adapter's
``block_variations`` hook reads which, :class:`portkit.adapters.VariationSet`).
Each registered variant becomes a Bedrock block of its own, decided by
Alex's picks on #296 (pending; the 'a' options are built):

1. **Block id** ``<blockstate>_<variant>`` (the variant key as written; a key
   Bedrock's identifier grammar refuses stays residue, never renamed).
2. **Display name** the Java name of the block that variant belongs to, read
   from the jar's 1.12 ``lang/*.lang`` under the key the adapter read, without
   the per-variation tooltip.
3. **Connected-texture variations** stay ``connected_texture`` residue: a
   variant whose model chain is a Connected Textures Mod model
   (``ctm_version``/``ctm_overrides``) or that wears a texture whose sidecar
   carries a ``ctm`` section and no animation (as
   :func:`portkit.converters.textures.convert` refuses it).
4. **Variations gated on another mod** (or on a branch the reading can't
   decide) stay ``conditional_block`` residue.
5. **A mixed blockstate file** counts as converted when any variation
   converts; the note names each variant left behind and why.

A variant is read as Forge's blockstate loader v1 reads it
(``ForgeBlockStateV1``, Forge 1.12.x): an array value is a fully specified
variant (one entry; several are weighted alternates, left as residue), its
``model`` and ``textures`` inherit the ``defaults`` entry's (``Variant#sync``:
a key the variant sets wins), and a model name ``ns:path`` names
``ns:block/path`` (``Variant.Deserializer#getBlockLocation``; a bare name is
minecraft's). Any other key (a rotation, uvlock, submodels, custom data)
stays residue with that reason. A variant the blockstate has and the code
doesn't register is never converted (Java registers no block for it); one
the code registers that the blockstate lacks is said.
"""
from __future__ import annotations

import json
import re

from ..model import ConversionResult, SourceMod, Unhandled
from . import models
from .textures import CONNECTED_TEXTURE, CTM_SECTION

CONDITIONAL_BLOCK = "conditional_block"
_ID = re.compile(r"^[a-z0-9_.-]+$")
_READ = frozenset({"model", "textures"})


def _model_name(name: str) -> str:
    ns, _, path = name.rpartition(":")
    return f"{ns or 'minecraft'}:block/{path}"


def _entry(variants: dict, defaults: dict, key: str) -> tuple[dict | None, str]:
    """(the composed {parent, textures} model of variant ``key``, or why not)."""
    value = variants.get(key)
    if isinstance(value, list):
        if len(value) != 1:
            return None, f"{len(value)} weighted alternates"
        value = value[0]
    if not isinstance(value, dict):
        return None, "not a fully specified variant"
    for part in (defaults, value):
        extra = sorted(set(part) - _READ)
        if extra:
            return None, f"sets {', '.join(extra)}, which the variation path doesn't read"
    model = value["model"] if "model" in value else defaults.get("model")
    if not isinstance(model, str):
        return None, "names no model"
    textures = {**(defaults.get("textures") or {}), **(value.get("textures") or {})}
    if not all(isinstance(v, str) and v for v in textures.values()):
        return None, "removes or misnames a texture"
    return {"parent": _model_name(model), "textures": textures}, ""


def _ctm(mod: SourceMod, model: dict) -> str:
    """Why a composed model is drawn by the Connected Textures Mod, or ""."""
    flat, parents, _why = models.resolve(mod, model)
    for path in parents:
        try:
            body = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(body, dict) and ("ctm_overrides" in body or "ctm_version" in body):
            return (f"its model {path.relative_to(mod.assets).as_posix()} is a Connected Textures Mod model "
                    "(ctm_version/ctm_overrides), which picks faces from the neighbours")
    for slot, ref in sorted((flat.get("textures") or {}).items()):
        if slot == "particle" or not isinstance(ref, str) or ref.startswith("#"):
            continue
        ns, _, path = ref.rpartition(":")
        if (ns or "minecraft") != mod.namespace:
            continue
        sidecar = mod.assets / "textures" / f"{path}.png.mcmeta"
        try:
            meta = json.loads(sidecar.read_text()) if sidecar.is_file() else None
        except (OSError, json.JSONDecodeError):
            meta = None
        if isinstance(meta, dict) and CTM_SECTION in meta and "animation" not in meta:
            return (f"its texture {ref!r} carries a {CTM_SECTION!r} sidecar section: the Connected Textures "
                    "Mod draws it from the neighbours")
    return ""


def read_lang(mod: SourceMod) -> dict[str, dict[str, str]]:
    """Bedrock locale -> {key: text} of the jar's 1.12 ``lang/*.lang``
    files (``key=value`` lines; ``#`` comments and lines with no ``=``
    skipped, as 1.12 ``LanguageMap`` reads them). Locales Bedrock has no
    slot for are left out."""
    from .lang import _LOCALES
    out: dict[str, dict[str, str]] = {}
    src = mod.assets / "lang"
    if not src.is_dir():
        return out
    for path in sorted(src.glob("*.lang")):
        bedrock = _LOCALES.get(path.stem.lower())
        if bedrock is None:
            continue
        entries: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            entries.setdefault(key, value)
        out[bedrock] = entries
    return out


def convert(mod: SourceMod, result: ConversionResult, rel: str, name: str, blockstate: dict,
            vset, lang: dict, model_block, block_definition) -> dict:
    """Convert the registered variants of blockstate ``name`` (see the module
    docstring); ``model_block`` is :func:`portkit.converters.blocks._model_dict_block`
    and ``block_definition`` :func:`portkit.converters.blocks._block_definition`.
    Returns the record the notes are written from."""
    record = {"name": name, "converted": [], "left": {}, "unregistered": [], "kinds": set(),
              "why": vset.why}
    variants = blockstate.get("variants")
    if blockstate.get("forge_marker") != 1 or not isinstance(variants, dict) or "multipart" in blockstate:
        why = "the blockstate isn't a Forge blockstate (forge_marker 1) with variants"
        result.unhandled.append(Unhandled(rel, "block", f"{why}; {vset.why}" if vset.why else why))
        return record
    defaults = blockstate.get("defaults") or {}
    registered = {v.name for v in vset.variations}
    record["unregistered"] = sorted(k for k in variants if k not in registered)
    lines: dict[str, list[str]] = {}
    for v in vset.variations:
        ident = f"{name}_{v.name}"
        if v.gate:
            record["left"][v.name] = (CONDITIONAL_BLOCK, v.gate)
            continue
        if v.name not in variants:
            record["left"][v.name] = ("block", "the code registers it but the blockstate has no such variant "
                                               "(Java draws its missing model)")
            continue
        if not _ID.match(v.name):
            record["left"][v.name] = ("block", f"{ident!r} isn't a valid Bedrock identifier")
            continue
        model, why = _entry(variants, defaults, v.name)
        if model is None:
            record["left"][v.name] = ("block", f"variant {v.name!r} {why}")
            continue
        ctm = _ctm(mod, model)
        if ctm:
            record["left"][v.name] = (CONNECTED_TEXTURE, ctm)
            continue
        claimed = set(result.consumed)
        geometry, instances, geo, why = model_block(mod, result, model, f"{name}#{v.name}", ident)
        if geometry is None:
            result.consumed = claimed
            record["left"][v.name] = ("block", why)
            continue
        if geo is not None:
            result.files[f"models/blocks/{ident}.geo.json"] = geo
        result.files[f"blocks/{ident}.json"] = block_definition(mod.namespace, ident, geometry, instances or {})
        record["converted"].append(v.name)
        for bedrock, entries in lang.items():
            text = entries.get(v.lang_key) if v.lang_key else None
            if text:
                lines.setdefault(bedrock, []).append(f"tile.{mod.namespace}:{ident}.name={text.strip()}")
    for bedrock, ls in sorted(lines.items()):
        path = f"texts/{bedrock}.lang"
        had = (result.files.get(path) or "").splitlines()
        result.files[path] = "".join(f"{x}\n" for x in sorted(set(had) | set(ls)))
    if lines:
        both = set(result.files.get("texts/languages.json") or []) | set(lines)
        result.files["texts/languages.json"] = (["en_US"] if "en_US" in both else []) + \
            sorted(b for b in both if b != "en_US")
    if not record["converted"]:
        kinds = {k for k, _ in record["left"].values()}
        kind = kinds.pop() if len(kinds) == 1 else "block"
        parts = [f"{k}: {w}" for k, (_, w) in record["left"].items()]
        if vset.why:
            parts.append(vset.why)
        if not parts:
            parts.append("the code registers none of its variants")
        result.unhandled.append(Unhandled(rel, kind, "no registered variation converts (" + "; ".join(parts) + ")"))
    return record


def notes(records: list[dict]) -> list[str]:
    out = []
    for r in records:
        if not r["converted"]:
            continue
        left = "; ".join(f"{k} ({kind}: {why})" for k, (kind, why) in r["left"].items())
        unreg = ", ".join(r["unregistered"])
        out.append(
            f"{r['name']}: {len(r['converted'])} registered variation(s) converted as {r['name']}_<variant> "
            f"({', '.join(r['converted'])}), named as Java names the block (the per-variation tooltip "
            "is not shown)"
            + (f"; left: {left}" if left else "")
            + (f"; in the blockstate but not registered by the mod's code: {unreg}" if unreg else "")
            + (f"; {r['why']}" if r["why"] else ""))
    return out
