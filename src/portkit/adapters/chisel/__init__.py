"""Chisel (#296): the block variations its ``Features`` builder chains register.

Chisel 1.12 (Chisel-Team/Chisel, branch 1.12/dev; jar
``Chisel-MC1.12.2-1.0.2.45``) ships one blockstate per block family with one
bare variant per variation (``assets/chisel/blockstates/andesite.json``:
``"variants": {"cracked": [{...}], ...}``), and registers the variations
from code, not data:

* ``team.chisel.Features`` is an enum with one constant per feature; each
  constant's own ``addBlocks(ChiselBlockFactory)`` makes its blocks with a
  builder chain::

      factory.newBlock(Material.ROCK, "andesite", provider)
              .newVariation("cracked").next("bricks-soft") ... .build(...);

  ``ChiselBlockFactory#newBlock(material, blockName, [group,] provider)``
  (or ``(material, blockName, creator, blockClass[, itemBlockClass])``)
  starts a ``ChiselBlockBuilder``; ``setParentFolder(folder)`` changes its
  folder (the block name until then); ``newVariation(name[, group])`` starts
  a ``VariationBuilder``, whose ``next(name[, group])`` adds it and starts
  the next one, ``buildVariation()`` adds it and returns the block builder,
  and ``build(...)`` adds it and registers the block(s).
* ``Features.loadBlocks`` calls ``addBlocks`` only for an enabled feature:
  ``Features#enabled`` = ``Configurations.featureEnabled(this) &&
  hasRequiredMod() && hasParentFeature()``. ``hasRequiredMod`` is
  ``requiredMod == null || Loader.isModLoaded(requiredMod)``, the
  ``requiredMod`` the constant's constructor takes (``BLOODMAGIC("bloodmagic")``);
  ``hasParentFeature`` is ``parent == null || parent.enabled()``.
  ``Configurations.featureEnabled`` reads the config with default ``true``
  (``Configurations.java`` line 122): **DEFAULT**, every feature is enabled,
  as Chisel's config ships.
* A block whose state has one property (``BlockCarvable``: its constructor
  builds ``new BlockStateContainer(this, metaProp)``, the one ``variation``
  property, ``BlockCarvable.java`` lines 71-72) is drawn by
  ``ChiselModelRegistry.ChiselStateMapper``: blockstate file
  ``chisel:<folder>``, variant ``<name>`` (the variation's path
  ``<folder>/<name>`` split at its last slash). A block class with more
  properties draws from ``chisel:<folder>/<name>`` instead, so only
  ``BlockCarvable`` chains are offered as variations of ``<folder>``.
* The block's translation key: ``ChiselBlockBuilder#build`` sets the
  unlocalized name ``domain + '.' + blockName``, the domain being the one
  ``ChiselBlockFactory.newFactory(registry, Chisel.MOD_ID)`` was made with
  (a compile-time constant, an ``ldc`` at the call), so the item's name is
  ``tile.<domain>.<blockName>.name`` (1.12 ``Block#getUnlocalizedName``
  adds ``tile.``, ``ItemBlock`` the ``.name``).

:func:`block_variations` runs each ``addBlocks`` on the core's interpreter
(:class:`portkit.blockcode.Machine`) with the builder calls read as above
through its ``call_hook``; a call into Chisel's own code that touches no
builder (``Carving.chisel.addVariation``, ``CarvingUtils.addOreGroup``) is
not followed, since it registers nothing the variations are read from. What
the reading can't pin (a name that isn't a string, a chain on one way of a
branch it can't decide, a feature constant it can't read) is said, never
guessed.
"""
from __future__ import annotations

from .. import Adapter, Variation, VariationSet

_FACTORY = "team/chisel/api/block/ChiselBlockFactory"
_BUILDER = "team/chisel/api/block/ChiselBlockBuilder"
_VARIATION = "team/chisel/api/block/ChiselBlockBuilder$VariationBuilder"
_CARVABLE = "team/chisel/common/block/BlockCarvable"
_ADD_BLOCKS = f"(L{_FACTORY};)V"
# The reading's own stand-ins for the factory, a block builder and a
# variation builder.
_F, _B, _V = "__chisel_factory", "__chisel_block", "__chisel_variation"


def _params(desc: str) -> list[str]:
    out, i = [], 1
    while desc[i] != ")":
        j = i
        while desc[j] == "[":
            j += 1
        j = desc.index(";", j) + 1 if desc[j] == "L" else j + 1
        out.append(desc[i:j])
        i = j
    return out


def _domain(classes) -> str:
    """The domain ``ChiselBlockFactory.newFactory(registry, domain)`` is
    called with, when every call passes the same constant string."""
    from ...bytecode import instructions
    found = set()
    for name in classes.names():
        if _FACTORY.encode() not in (classes.raw(name) or b""):
            continue
        cf = classes.get(name)
        for m in cf.methods if cf else ():
            if m.code is None:
                continue
            code = instructions(cf, m.code)
            for k, i in enumerate(code):
                ref = i.arg
                if i.op == 0xB8 and getattr(ref, "owner", None) == _FACTORY and ref.name == "newFactory":
                    prev = code[k - 1] if k else None
                    found.add(prev.arg if prev is not None and prev.op in (0x12, 0x13)
                              and isinstance(prev.arg, str) else None)
    return found.pop() if len(found) == 1 and None not in found else ""


class _Reading:
    def __init__(self, machine):
        self.machine = machine
        self.chains: list[dict] = []
        self.following = False

    def block_class(self, provider) -> str | None:
        from ...blockcode import ClassLit, Obj, Unreadable
        if isinstance(provider, ClassLit):
            return provider.name
        if not isinstance(provider, Obj):
            return None
        self.following = True
        try:
            got = self.machine.call(provider.cls, "getBlockClass", "()Ljava/lang/Class;", [provider])
        except Unreadable:
            got = []
        finally:
            self.following = False
        return got[0].name if len(got) == 1 and isinstance(got[0], ClassLit) else None

    def finish(self, chain) -> None:
        f = chain.fields
        self.chains.append({"name": f["name"], "folder": f["folder"], "cls": f["cls"],
                            "variations": list(f["variations"]), "unread": list(f["unread"]),
                            "forked": f["forked"] or self.machine._forked})

    def hook(self, owner, mname, desc, args, static):
        from ...blockcode import Obj, UNKNOWN
        recv = None if static or not args else args[0]
        ret = desc.rsplit(")", 1)[-1]
        rest = list(args[1:]) if recv is not None else list(args)
        if isinstance(recv, Obj) and recv.cls == _F:
            if mname != "newBlock":
                return [None] if ret == "V" else [UNKNOWN]
            params = _params(desc)
            name = rest[1] if len(rest) > 1 else None
            if params[2:3] == ["Lteam/chisel/api/block/BlockCreator;"]:
                cls = self.block_class(rest[3] if len(rest) > 3 else None)
            else:
                cls = self.block_class(rest[-1] if rest else None)
            unread = [] if isinstance(name, str) else ["the block name isn't read"]
            return [Obj(_B, {"name": name if isinstance(name, str) else None,
                             "folder": name if isinstance(name, str) else None, "cls": cls,
                             "variations": [], "unread": unread, "forked": self.machine._forked})]
        if isinstance(recv, Obj) and recv.cls == _B:
            f = recv.fields
            if mname == "setParentFolder" and rest:
                if isinstance(rest[0], str):
                    f["folder"] = rest[0]
                else:
                    f["folder"] = None
                    f["unread"].append("the parent folder isn't read")
                return [recv]
            if mname == "newVariation" and rest:
                return [self.variation(recv, rest[0])]
            if mname == "build":
                self.finish(recv)
                return [UNKNOWN]
            return [recv] if ret == f"L{_BUILDER};" else [None] if ret == "V" else [UNKNOWN]
        if isinstance(recv, Obj) and recv.cls == _V:
            chain = recv.fields["chain"]
            if mname in ("next", "buildVariation", "build"):
                self.add(recv)
                if mname == "next" and rest:
                    return [self.variation(chain, rest[0])]
                if mname == "build":
                    self.finish(chain)
                    return [UNKNOWN]
                return [chain]
            return [recv] if ret == f"L{_VARIATION};" else [None] if ret == "V" else [UNKNOWN]
        if self.following or mname in ("<init>", "<clinit>") or not self.machine.is_mod(owner) \
                or ret in (f"L{_BUILDER};", f"L{_VARIATION};"):
            return None
        if any(isinstance(a, Obj) and a.cls in (_F, _B, _V) for a in args):
            return None  # a helper handed the factory or a builder is followed
        # Chisel's own code that touches no builder (its carving registry,
        # ore groups, recipes): registers no variation, not followed.
        return [None] if ret == "V" else [UNKNOWN]

    def variation(self, chain, name):
        from ...blockcode import Obj
        if not isinstance(name, str):
            chain.fields["unread"].append("a variation name isn't read")
        return Obj(_V, {"chain": chain, "name": name if isinstance(name, str) else None, "added": False})

    @staticmethod
    def add(var) -> None:
        if not var.fields["added"]:
            var.fields["added"] = True
            if var.fields["name"] is not None:
                var.fields["chain"].fields["variations"].append(var.fields["name"])


def _gate(machine, const, seen=()) -> str:
    """Why Java may not run the feature's addBlocks: its required mod, or
    its parent feature's, or that the constant isn't read ("" when neither)."""
    from ...blockcode import Obj
    if not isinstance(const, Obj):
        return "the feature's enum constant isn't read, so whether it needs another mod isn't known"
    mod = const.fields.get("requiredMod")
    if isinstance(mod, str):
        return (f"the feature registers its blocks only when mod {mod!r} is loaded "
                "(Chisel's Features#hasRequiredMod: Loader.isModLoaded)")
    if mod is not None:
        return "the feature's required mod isn't read"
    parent = const.fields.get("parent")
    if parent is not None:
        if not isinstance(parent, Obj) or id(parent) in seen:
            return "the feature's parent feature isn't read"
        why = _gate(machine, parent, seen + (id(parent),))
        return f"its parent feature: {why}" if why else ""
    return ""


def read(classes) -> tuple[dict, list[str]]:
    """(blockstate folder -> VariationSet, reasons a feature couldn't be read)."""
    from ...blockcode import Machine, Obj, UNKNOWN, Unreadable
    from ...rendershape import _dotted
    owners = []
    for name in classes.names():
        if _FACTORY.encode() not in (classes.raw(name) or b"") or classes.is_library(name):
            continue
        cf = classes.get(name)
        m = cf and cf.method("addBlocks", _ADD_BLOCKS)
        if m is not None and m.code is not None and not (m.access & 0x0008):
            owners.append((cf, m))
    if not owners:
        return {}, []
    domain = _domain(classes)
    machine = Machine(classes)
    reading = _Reading(machine)
    machine.call_hook = reading.hook
    problems: list[str] = []
    consts: dict[str, object] = {}
    for base in sorted({cf.super_name for cf, _ in owners if cf.super_name}):
        machine.steps = 0
        machine.init_class(base)
        if base in machine._clinit_failed:
            problems.append(f"{_dotted(base)}'s class initializer can't be followed to the end")
    for (owner, field), value in machine.statics.items():
        if isinstance(value, Obj) and any(value.cls == cf.name for cf, _ in owners):
            consts.setdefault(value.cls, value)
    out: dict[str, dict] = {}
    for cf, m in sorted(owners, key=lambda t: t[0].name):
        const = consts.get(cf.name)
        if const is None and cf.super_name is not None and cf.name in {c.super_name for c, _ in owners}:
            continue  # the enum itself: its addBlocks is the empty default
        gate = _gate(machine, const)
        where = f"{_dotted(cf.name)}#addBlocks"
        start = len(reading.chains)
        machine.steps = 0
        machine.new_epoch()
        try:
            machine.run(cf, m, [const if const is not None else UNKNOWN, Obj(_F, {})])
        except Unreadable as exc:
            problems.append(f"{where} can't be followed to the end ({exc})")
            continue
        for chain in reading.chains[start:]:
            folder = chain["folder"]
            if folder is None:
                problems.append(f"a chain in {where}: {'; '.join(chain['unread']) or 'its folder is not read'}")
                continue
            entry = out.setdefault(folder, {"vars": {}, "why": [], "where": where})
            if chain["cls"] != _CARVABLE:
                entry["why"].append(
                    f"{where} makes it with block class "
                    f"{_dotted(chain['cls']) if chain['cls'] else '(not read)'}, not BlockCarvable: whether its state "
                    "has the one variation property, which ChiselStateMapper draws from this blockstate, "
                    "isn't read (a block with more draws from a blockstate per variation)")
                continue
            if chain["unread"]:
                entry["why"].append(f"a chain in {where}: {'; '.join(chain['unread'])}")
            own = gate or ("its chain runs on one way of a branch the reading can't decide"
                           if chain["forked"] else "")
            key = f"tile.{domain}.{chain['name']}.name" if domain and chain["name"] else ""
            for v in chain["variations"]:
                entry["vars"].setdefault(v, Variation(v, key, own, f"{where} (block {chain['name']!r})"))
    sets = {folder: VariationSet(tuple(e["vars"].values()), "; ".join(dict.fromkeys(e["why"])), e["where"])
            for folder, e in out.items()}
    return sets, problems


def block_variations(mod) -> dict:
    classes = getattr(mod, "classes", None)
    if classes is None or not len(classes) or not classes.mentions(_FACTORY.encode()):
        return {}
    sets, _problems = read(classes)
    return sets


ADAPTER = Adapter(
    name="chisel",
    namespaces=frozenset({"chisel"}),
    block_variations=block_variations,
)
