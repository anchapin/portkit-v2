"""Quark (#296): the registry aliases its code adds for its old block ids.

Quark 4.1 (Minecraft 1.21.1) no longer has some blocks it once added because
vanilla now has them (the crafter, tuff and bamboo blocks). Its
``QuarkRemapHandler`` keeps the old ids loading: ``<clinit>`` fills the
static map ``REMAP`` with ``"quark:<name>" -> "minecraft:<name>"`` pairs, and
``onRemapBlocks`` (a ``@LoadEvent`` handler for Zeta's ``ZRegister``) calls
``BuiltInRegistries.BLOCK.addAlias`` and ``BuiltInRegistries.ITEM.addAlias``
with each pair (Quark 4.1-487, read with ``portkit.bytecode``). The jar still
ships ``assets/quark/blockstates/crafter.json``, whose id is so aliased.

The pairs are read from the bytecode only when the class has exactly that
shape: every write to ``REMAP`` is a ``Map.put`` of two string constants in
``<clinit>``, ``onRemapBlocks`` carries ``@LoadEvent``, reads ``REMAP`` and
calls ``addAlias`` after reading ``BuiltInRegistries.BLOCK``, and another of
the mod's classes names the handler class (its subscription). Anything else
reads nothing (#87). Which blocks Quark does register is not read here; the
core says an aliased blockstate is residue only where its own registration
reader found no block under the name.
"""
from __future__ import annotations

import weakref

from ... import bytecode
from .. import Adapter, BlockAlias

HANDLER = "org/violetmoon/quark/base/handler/QuarkRemapHandler"
_FIELD = "REMAP"
_METHOD = "onRemapBlocks"
_LOAD_EVENT = "Lorg/violetmoon/zeta/event/bus/LoadEvent;"
_REGISTRIES = "net/minecraft/core/registries/BuiltInRegistries"
_GETSTATIC, _PUTSTATIC, _LDC = 0xB2, 0xB3, frozenset((0x12, 0x13))
_INVOKES = frozenset((0xB6, 0xB7, 0xB8, 0xB9))

_READ: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def read_aliases(classes) -> dict[str, str]:
    """``{"quark:<name>": "<target id>"}`` the handler aliases, or {} when the
    class isn't there or isn't in the shape the module docstring gives."""
    if classes is None:
        return {}
    cf = classes.get(HANDLER)
    if cf is None:
        return {}
    pairs: dict[str, str] = {}
    handler_ok = False
    for m in cf.methods:
        if m.code is None:
            continue
        insns = bytecode.instructions(cf, m.code)
        for k, ins in enumerate(insns):
            ref = ins.arg if isinstance(ins.arg, bytecode.Ref) else None
            if ref is None or ref.owner != HANDLER or ref.name != _FIELD:
                continue
            if ins.op == _PUTSTATIC and m.name != "<clinit>":
                return {}
            if ins.op != _GETSTATIC or m.name == _METHOD:
                continue
            if m.name != "<clinit>":
                return {}  # REMAP read anywhere else might be changed there
            nxt = insns[k + 1:k + 4]
            if len(nxt) == 3 and all(x.op in _LDC and isinstance(x.arg, str) for x in nxt[:2]) \
                    and nxt[2].op in _INVOKES and isinstance(nxt[2].arg, bytecode.Ref) \
                    and nxt[2].arg.name == "put":
                pairs[nxt[0].arg] = nxt[1].arg
            elif not (len(nxt) >= 1 and nxt[0].op == _PUTSTATIC):
                return {}
        if m.name == _METHOD:
            reads = any(isinstance(i.arg, bytecode.Ref) and i.op == _GETSTATIC
                        and i.arg.owner == HANDLER and i.arg.name == _FIELD for i in insns)
            block_alias = False
            seen_block = False
            for i in insns:
                if isinstance(i.arg, bytecode.Ref) and i.op == _GETSTATIC and i.arg.owner == _REGISTRIES:
                    seen_block = i.arg.name == "BLOCK"
                elif seen_block and isinstance(i.arg, bytecode.Ref) and i.op in _INVOKES \
                        and i.arg.name == "addAlias":
                    block_alias = True
            handler_ok = reads and block_alias and _LOAD_EVENT in (m.annotations or {})
    if not handler_ok or not _subscribed(classes):
        return {}
    return pairs


def _subscribed(classes) -> bool:
    """Whether another class of the jar names the handler class (as Zeta's
    load bus subscription does, ``CommonProxy``)."""
    needle = HANDLER.encode()
    for name in classes.names():
        raw = classes.raw(name)
        if name == HANDLER or raw is None or needle not in raw:
            continue
        cf = classes.get(name)
        if cf is None:
            continue
        for m in cf.methods:
            if m.code is None:
                continue
            for i in bytecode.instructions(cf, m.code):
                if i.op in _LDC and i.arg == ("class", HANDLER):
                    return True
    return False


def block_aliases(mod) -> dict[str, BlockAlias]:
    classes = getattr(mod, "classes", None)
    if classes is None or getattr(mod, "namespace", None) != "quark":
        return {}
    found = _READ.get(classes)
    if found is None:
        found = _READ[classes] = read_aliases(classes)
    where = (f"{HANDLER.replace('/', '.')}#{_METHOD} (BuiltInRegistries.BLOCK.addAlias over the pairs "
             f"<clinit> puts in {_FIELD})")
    return {k.partition(":")[2]: BlockAlias(v, where) for k, v in found.items() if k.startswith("quark:")}


ADAPTER = Adapter(
    name="quark",
    namespaces=frozenset({"quark"}),
    block_aliases=block_aliases,
)
