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
  ``<folder>/<name>`` split at its last slash), both lowercased as 1.12's
  ``ResourceLocation`` and ``ModelResourceLocation`` take them. A block class with more
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

from .. import Adapter, BlockRegistry, Variation, VariationSet

_FACTORY = "team/chisel/api/block/ChiselBlockFactory"
_BUILDER = "team/chisel/api/block/ChiselBlockBuilder"
_VARIATION = "team/chisel/api/block/ChiselBlockBuilder$VariationBuilder"
_CARVABLE = "team/chisel/common/block/BlockCarvable"
_ADD_BLOCKS = f"(L{_FACTORY};)V"
# The reading's own stand-ins for the factory, a block builder and a
# variation builder.
_F, _B, _V = "__chisel_factory", "__chisel_block", "__chisel_variation"
# The block registry ``ChiselBlockFactory#getRegistry`` hands back, and the
# field a block's ``setRegistryName(String)`` name is kept under (a block
# registered straight on the registry, as ``Features.AUTOCHISEL`` registers
# ``BlockAutoChisel``).
_R, _N = "__chisel_registry", "__chisel_named"
_REGISTRIES = "net/minecraftforge/fml/common/registry/ForgeRegistries"
_BLOCK_EVENT = b"RegistryEvent$Register<Lnet/minecraft/block/Block;>"


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
        self.clinit_why = ""
        # Names registered straight on the factory's registry, and why such a
        # registration (or another registration call) wasn't read.
        self.direct: list[str] = []
        self.direct_why: list[str] = []

    def block_class(self, provider) -> tuple[str | None, str]:
        """(the block class a provider (or a class literal) names, or why not)."""
        from ...blockcode import ClassLit, Obj, Unreadable
        if isinstance(provider, ClassLit):
            return provider.name, ""
        if not isinstance(provider, Obj):
            why = "the provider handed to newBlock isn't read"
            return None, f"{why} ({self.clinit_why})" if self.clinit_why else why
        self.following = True
        try:
            got = self.machine.call(provider.cls, "getBlockClass", "()Ljava/lang/Class;", [provider])
        except Unreadable as exc:
            return None, f"the provider's getBlockClass can't be followed ({exc})"
        finally:
            self.following = False
        if len(got) == 1 and isinstance(got[0], ClassLit):
            return got[0].name, ""
        return None, "the provider's getBlockClass isn't read"

    def finish(self, chain) -> None:
        f = chain.fields
        self.chains.append({"name": f["name"], "folder": f["folder"], "cls": f["cls"], "cls_why": f["cls_why"],
                            "variations": list(f["variations"]), "unread": list(f["unread"]),
                            "forked": f["forked"] or self.machine._forked})

    def hook(self, owner, mname, desc, args, static):
        from ...blockcode import Obj, UNKNOWN
        recv = None if static or not args else args[0]
        ret = desc.rsplit(")", 1)[-1]
        rest = list(args[1:]) if recv is not None else list(args)
        if isinstance(recv, Obj) and recv.cls == _F and mname == "getRegistry":
            return [Obj(_R, {})]
        if isinstance(recv, Obj) and recv.cls == _R:
            named = rest[0].fields.get(_N) if len(rest) == 1 and isinstance(rest[0], Obj) else None
            if mname == "register" and isinstance(named, str):
                self.direct.append(named.lower())
            else:
                self.direct_why.append(f"a call {mname} on the block registry isn't read as a registration")
            return [None] if ret == "V" else [UNKNOWN]
        if mname == "setRegistryName" and recv is not None and desc.startswith("(Ljava/lang/String;)") \
                and not self.following:
            # The name rides on the block itself, which the call returns, so
            # a chain that goes on (setCreativeTab, ...) keeps the object.
            name = rest[0] if rest else None
            if isinstance(recv, Obj):
                recv.fields[_N] = name if isinstance(name, str) else None
                return [recv]
            return [UNKNOWN]
        if mname in ("register", "registerAll") and not self.following:
            self.direct_why.append(f"a registration call {owner.replace('/', '.')}#{mname} isn't read")
        if isinstance(recv, Obj) and recv.cls == _F:
            if mname != "newBlock":
                return [None] if ret == "V" else [UNKNOWN]
            params = _params(desc)
            name = rest[1] if len(rest) > 1 else None
            if params[2:3] == ["Lteam/chisel/api/block/BlockCreator;"]:
                cls, cls_why = self.block_class(rest[3] if len(rest) > 3 else None)
            else:
                cls, cls_why = self.block_class(rest[-1] if rest else None)
            unread = [] if isinstance(name, str) else ["the block name isn't read"]
            return [Obj(_B, {"name": name if isinstance(name, str) else None,
                             "folder": name if isinstance(name, str) else None, "cls": cls, "cls_why": cls_why,
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
        if any(isinstance(a, Obj) and a.cls in (_F, _B, _V, _R) for a in args):
            return None  # a helper handed the factory or a builder is followed
        found = self.machine.find_method(owner, mname, desc)
        if found is not None and found[1].access & 0x1000:
            # A synthetic method (javac 8's access$NNN, through which a
            # constant's body reads Features' private provider fields; a
            # lambda body) is followed: it is the read, not a registry.
            return None
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
    sets, problems, _registry = _cached(classes)
    return sets, problems


_LAST: list = []


def _cached(classes):
    """:func:`_read` of the last ``classes`` asked (one conversion asks
    twice: block_variations and block_registry)."""
    if _LAST and _LAST[0] is classes:
        return _LAST[1]
    got = _read(classes)
    _LAST[:] = [classes, got]
    return got


def _read(classes) -> tuple[dict, list[str], dict]:
    """:func:`read`, and what the registry reading needs: {"names": every
    folder a chain was read with and every name registered straight on the
    registry (lowercased), "why": why a registration may have been missed,
    "bases": the enum classes whose constants were read}."""
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
        return {}, [], {"names": set(), "why": ["no feature's addBlocks is found"], "bases": set()}
    domain = _domain(classes)
    machine = Machine(classes)
    reading = _Reading(machine)
    machine.call_hook = reading.hook
    problems: list[str] = []
    consts: dict[str, object] = {}
    for base in sorted({cf.super_name for cf, _ in owners if cf.super_name}):
        # The enum's class initializer (its constants, then its provider
        # fields), run as Machine.init_class runs it, keeping why it stopped.
        bcf = classes.get(base)
        clinit = bcf and bcf.method("<clinit>", "()V")
        if base in machine._clinit_done or clinit is None or clinit.code is None:
            continue
        machine._clinit_done.add(base)
        if bcf.super_name:
            machine.init_class(bcf.super_name)
        machine.steps = 0
        machine.new_epoch()
        machine._clinit_depth += 1
        try:
            machine.run(bcf, clinit, [])
        except Unreadable as exc:
            machine._clinit_failed.add(base)
            reading.clinit_why = f"{_dotted(base)}'s class initializer can't be followed to the end ({exc})"
            problems.append(reading.clinit_why)
        finally:
            machine._clinit_depth -= 1
    for (owner, field), value in machine.statics.items():
        if isinstance(value, Obj) and any(value.cls == cf.name for cf, _ in owners):
            consts.setdefault(value.cls, value)
    out: dict[str, dict] = {}
    names: set[str] = set()
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
            if folder is not None:
                names.add(folder.lower())
            if folder is None:
                problems.append(f"a chain in {where}: {'; '.join(chain['unread']) or 'its folder is not read'}")
                continue
            # Java asks the blockstate for the location and variant lowercased
            # (1.12 ResourceLocation; "the variant string is silently
            # toLowerCase'd", Forge 1.12.x docs, Connecting Blocks and Items
            # to Models): registered "screenMetallic" is variant "screenmetallic".
            folder = folder.lower()
            entry = out.setdefault(folder, {"vars": {}, "why": [], "where": where})
            if chain["cls"] is None:
                entry["why"].append(f"{where}: the block class isn't read ({chain['cls_why']}), so whether its "
                                    "state has the one variation property ChiselStateMapper draws from this "
                                    "blockstate isn't known")
                continue
            if chain["cls"] != _CARVABLE:
                entry["why"].append(
                    f"{where} makes it with block class {_dotted(chain['cls'])}, not BlockCarvable: whether its "
                    "state has the one variation property, which ChiselStateMapper draws from this blockstate, "
                    "isn't read (a block with more draws from a blockstate per variation)")
                continue
            if chain["unread"]:
                entry["why"].append(f"a chain in {where}: {'; '.join(chain['unread'])}")
            own = gate or ("its chain runs on one way of a branch the reading can't decide"
                           if chain["forked"] else "")
            key = f"tile.{domain}.{chain['name']}.name" if domain and chain["name"] else ""
            for v in chain["variations"]:
                entry["vars"].setdefault(v.lower(), Variation(v.lower(), key, own, f"{where} (block {chain['name']!r})"))
    sets = {folder: VariationSet(tuple(e["vars"].values()), "; ".join(dict.fromkeys(e["why"])), e["where"])
            for folder, e in out.items()}
    names.update(reading.direct)
    bases = {cf.super_name for cf, _ in owners if cf.super_name and cf.super_name in {c.name for c, _ in owners}}
    return sets, problems, {"names": names, "why": problems + reading.direct_why, "bases": bases}


def _other_paths(classes, bases: set) -> list[str]:
    """Why a block may be registered outside the features' ``addBlocks``
    (the reading :func:`_read` follows): a ``RegistryEvent.Register<Block>``
    handler in a class other than the features' enum (whose ``loadBlocks``
    hands every enabled feature the factory, ``Features.java`` L3319-3335 on
    Chisel-Team/Chisel 1.12/dev), a ``register``/``registerAll`` call in a
    method that reads ``ForgeRegistries.BLOCKS``, or a registry looked up or
    listened to by type (``GameRegistry.findRegistry``,
    ``addGenericListener``). Empty when the jar's own classes show none."""
    from ...bytecode import instructions
    from ...rendershape import _dotted
    out = []
    for name in classes.names():
        if classes.is_library(name):
            continue
        raw = classes.raw(name) or b""
        if _BLOCK_EVENT in raw and name not in bases:
            out.append(f"{_dotted(name)} handles RegistryEvent.Register<Block>, which the reading doesn't follow")
        if b"findRegistry" in raw or b"addGenericListener" in raw:
            out.append(f"{_dotted(name)} looks up or listens to a registry by type, which the reading doesn't "
                       "follow")
        if _REGISTRIES.encode() not in raw:
            continue
        cf = classes.get(name)
        for m in cf.methods if cf else ():
            if m.code is None:
                continue
            refs = [i.arg for i in instructions(cf, m.code)]
            blocks = any(getattr(r, "owner", None) == _REGISTRIES and getattr(r, "name", None) == "BLOCKS"
                         for r in refs)
            if blocks and any(getattr(r, "name", None) in ("register", "registerAll") for r in refs):
                out.append(f"{_dotted(name)}#{m.name} registers on ForgeRegistries.BLOCKS, which the reading "
                           "doesn't follow")
    return out


def block_variations(mod) -> dict:
    classes = getattr(mod, "classes", None)
    if classes is None or not len(classes) or not classes.mentions(_FACTORY.encode()):
        return {}
    sets, _problems = read(classes)
    return sets


def block_registry(mod):
    """The blockstate names Chisel's code registers blocks under (#296):
    every chain's folder (a ``BlockCarvable`` draws blockstate ``<folder>``;
    any other class is counted under its folder too, so it is never said to
    be missing) and every name registered straight on the factory's registry
    (``Features.AUTOCHISEL``: ``factory.getRegistry().register(new
    BlockAutoChisel().setRegistryName("auto_chisel"))``, Features.java
    L286-291), whatever feature gate it sits behind. ``why`` names every
    reason the reading may have missed one: a feature it couldn't follow, a
    chain whose folder it couldn't read, a registration call it doesn't read,
    a registration path outside ``addBlocks`` (:func:`_other_paths`), or a
    factory domain that isn't the jar's namespace."""
    classes = getattr(mod, "classes", None)
    if classes is None or not len(classes) or not classes.mentions(_FACTORY.encode()):
        return None
    _sets, _problems, reg = _cached(classes)
    why = list(reg["why"])
    domain = _domain(classes)
    if domain != mod.namespace:
        why.append(f"the factory's domain ({domain or 'not read'}) isn't the jar's namespace {mod.namespace!r}")
    why += _other_paths(classes, reg["bases"])
    return BlockRegistry(frozenset(reg["names"]), "; ".join(dict.fromkeys(why)),
                         "Chisel's Features#addBlocks builder chains and registry calls")


ADAPTER = Adapter(
    name="chisel",
    namespaces=frozenset({"chisel"}),
    block_variations=block_variations,
    block_registry=block_registry,
)
