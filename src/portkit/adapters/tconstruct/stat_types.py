"""Which Tinkers material stat types can repair a tool, read from the jar's classes.

A tool definition with no display-name module is named by the hook's default:
``ToolHooks.DISPLAY_NAME`` (Tinkers 3.12.1.231 @a5a03249,
``library/tools/definition/module/ToolHooks.java`` L134) defaults to a
``MaterialToolName`` that shows the materials whose slot stat type
``MaterialRegistry.getInstance().canRepair(statType)``. That is
``IMaterialRegistry#canRepair`` (L154-157): the registered
``MaterialStatType#canRepair``, which is ``defaultStats instanceof
IRepairableMaterialStats`` (``MaterialStatType`` L35, L45). So whether a stat
type names the tool is a property of its stats *class*, which only the
bytecode says.

This reads it generically: every class that implements ``IMaterialStats``
(through any chain of supertypes and interfaces) and builds a
``MaterialStatsId`` in its static initialiser, directly
(``new MaterialStatsId(TConstruct.getResource("head"))``,
``new MaterialStatsId("tconstruct", "plating_shield")``) or through one of its
own methods given a string constant (``PlatingMaterialStats.makeType(
"plating_helmet")``, ``RepairStats.makeType("laces")``, the
``StatlessMaterialStats`` enum constructor). A stat type declared that way is
taken to have default stats of its declaring class, which is how each Tinkers
stats class builds its ``TYPE`` (``new MaterialStatType<>(ID, new
HeadMaterialStats(...), ...)``, ``C::new`` lambdas, ``singleton(id, this)``).

The result maps each stat id read to whether it can repair; an id two classes
declare with different answers, and every id this cannot read, is left out, so
callers treat it as unknown.
"""
from __future__ import annotations

from ... import bytecode as bc

_PKG = "slimeknights/tconstruct/library/materials/stats/"
_STATS = _PKG + "IMaterialStats"
_REPAIRABLE = _PKG + "IRepairableMaterialStats"
_STATS_ID = _PKG + "MaterialStatsId"
_STR = "Ljava/lang/String;"


def _supertypes(classes, name: str) -> set[str]:
    seen, todo = set(), [name]
    while todo:
        cur = todo.pop()
        if cur in seen:
            continue
        seen.add(cur)
        cf = classes.get(cur)
        if cf is None:
            continue
        if cf.super_name:
            todo.append(cf.super_name)
        todo.extend(cf.interfaces)
    return seen


def _params(desc: str) -> list[str]:
    """Parameter descriptors of a method descriptor."""
    out, i, body = [], 0, desc[1 : desc.index(")")]
    while i < len(body):
        j = i
        while body[j] == "[":
            j += 1
        if body[j] == "L":
            j = body.index(";", j)
        out.append(body[i : j + 1])
        i = j + 1
    return out


def _last_slot(desc: str, static: bool) -> int:
    """The local-variable slot of a method's last parameter."""
    slot = 0 if static else 1
    params = _params(desc)
    for p in params[:-1]:
        slot += 2 if p in ("J", "D") else 1
    return slot


def _load_slot(insn) -> int | None:
    if insn.name == "aload":
        return insn.arg
    if insn.name.startswith("aload_"):
        return int(insn.name[-1])
    return None


def _namespace_helper(classes, ref) -> str | None:
    """A static ``m(String) -> ResourceLocation`` that is ``new RL(<ns>, arg0)``."""
    cf = classes.get(ref.owner)
    m = cf.method(ref.name, ref.desc) if cf is not None else None
    if m is None or not m.code or _params(ref.desc) != [_STR]:
        return None
    ins = [i for i in bc.instructions(cf, m.code)]
    names = [i.name for i in ins]
    if names[:2] != ["new", "dup"] or names[-1] != "areturn" or len(ins) != 6:
        return None
    if not isinstance(ins[2].arg, str) or _load_slot(ins[3]) != 0:
        return None
    init = ins[4].arg
    if ins[4].name != "invokespecial" or not isinstance(init, bc.Ref) or init.desc != f"({_STR}{_STR})V":
        return None
    return ins[2].arg


def _string(insn, param: tuple[int, str] | None) -> str | None:
    if insn.name in ("ldc", "ldc_w") and isinstance(insn.arg, str):
        return insn.arg
    slot = _load_slot(insn)
    if param is not None and slot == param[0]:
        return param[1]
    return None


def _ids(classes, cf, code, param=None) -> list[str]:
    """Every MaterialStatsId one method body builds from constants (or ``param``)."""
    ins = bc.instructions(cf, code)
    out = []
    for k, insn in enumerate(ins):
        ref = insn.arg
        if insn.name != "invokespecial" or not isinstance(ref, bc.Ref) \
                or ref.owner != _STATS_ID or ref.name != "<init>":
            continue
        params = _params(ref.desc)
        if params == [_STR, _STR] and k >= 2:
            ns, path = _string(ins[k - 2], param), _string(ins[k - 1], param)
            if ns is not None and path is not None:
                out.append(f"{ns}:{path}")
        elif params == [_STR] and k >= 1:
            full = _string(ins[k - 1], param)
            if full is not None and ":" in full:
                out.append(full)
        elif len(params) == 1 and params[0].startswith("L") and k >= 2:
            helper = ins[k - 1].arg
            if ins[k - 1].name == "invokestatic" and isinstance(helper, bc.Ref):
                ns = _namespace_helper(classes, helper)
                path = _string(ins[k - 2], param)
                if ns is not None and path is not None:
                    out.append(f"{ns}:{path}")
    return out


def _declared(classes, name: str) -> list[str]:
    """The stat ids a stats class declares in its static initialiser."""
    cf = classes.get(name)
    clinit = cf.method("<clinit>") if cf is not None else None
    if clinit is None or not clinit.code:
        return []
    out = _ids(classes, cf, clinit.code)
    ins = bc.instructions(cf, clinit.code)
    for k, insn in enumerate(ins):
        ref = insn.arg
        if insn.name not in ("invokestatic", "invokespecial") or not isinstance(ref, bc.Ref) \
                or ref.owner != name or k == 0:
            continue
        params = _params(ref.desc)
        if not params or params[-1] != _STR:
            continue
        value = _string(ins[k - 1], None)
        target = cf.method(ref.name, ref.desc)
        if value is None or target is None or not target.code:
            continue
        slot = _last_slot(ref.desc, static=insn.name == "invokestatic")
        out += _ids(classes, cf, target.code, (slot, value))
    return out


def repairable(classes) -> dict[str, bool]:
    """Stat id -> whether it can repair (so names a tool by default), from bytecode."""
    if classes is None or not hasattr(classes, "names"):
        return {}
    found: dict[str, set[bool]] = {}
    for name in classes.names():
        supers = _supertypes(classes, name)
        if _STATS not in supers or name in (_STATS, _REPAIRABLE):
            continue
        can = _REPAIRABLE in supers
        for stat in _declared(classes, name):
            found.setdefault(stat, set()).add(can)
    return {stat: next(iter(v)) for stat, v in sorted(found.items()) if len(v) == 1}
