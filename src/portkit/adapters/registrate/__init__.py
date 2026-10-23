"""Registrate (#362): block-entity renderers bound through its builder, as a library adapter.

A mod built on Registrate (tterrag1098/Registrate) declares a block entity
type with a builder chain in its own code, and Registrate binds the
renderer from Registrate's code, not the mod's, so the core's reader of the
client's registration calls (:func:`portkit.rendershape.bindings`) finds no
call in the mod. Read from Registrate MC1.20-1.3.3's bytecode (the copy
Create mc1.20.1-6.0.8 bundles in ``META-INF/jarjar/``):

* ``AbstractRegistrate#blockEntity([parent,] name, factory)`` starts a
  ``BlockEntityBuilder`` holding ``factory`` (a ``BlockEntityFactory``);
* ``BlockEntityBuilder#renderer(supplier)`` stores the supplier in the
  ``renderer`` field (the last call wins) and, the first time, on the client
  (``DistExecutor.unsafeRunWhenOn(Dist.CLIENT, ...)``), runs
  ``registerRenderer``, which adds an ``FMLClientSetupEvent`` listener
  (``lambda$registerRenderer$1``) calling
  ``BlockEntityRenderers.register(getEntry(), renderer.get()::apply)``;
* ``createEntry`` builds the type as
  ``BlockEntityType.Builder.of((pos, state) -> factory.create(type, pos, state), validBlocks).build(null)``.

So a chain ``blockEntity(name, factory)...renderer(supplier)...register()``
binds the renderer ``supplier.get()`` builds to the block entity ``factory``
makes.

The chain's ``register()`` (``AbstractBuilder#register``) returns the
``BlockEntityEntry`` ``createEntryWrapper`` wraps the registered object in,
and the entry's ``get()`` (``RegistryEntry#get``) is that registered
``BlockEntityType``, built by ``createEntry`` as above. A mod's block names
its type through the entry (Create's ``GaugeBlock#getBlockEntityType``:
``AllBlockEntityTypes.SPEEDOMETER.get()``), so while the core runs a block's
own no-argument method returning its type (#366,
:func:`portkit.rendershape.typed_entities`), :func:`block_entity_types`
reads the chain the same way and ``get()`` gives the type the core reads as a
built one: its factory is the chain's, with the type itself handed in first
(``factory.create(type, pos, state)``). Each method of the mod that calls ``BlockEntityBuilder#renderer`` is
run (a class initializer as the JVM runs it) with the builder calls read as
above; the renderer and block entity are read as the core reads a provider
and a factory. A chain whose factory or renderer isn't read binds nothing,
and the reason says why.
"""
from __future__ import annotations

from .. import Adapter

_REGISTRATE = "com/tterrag/registrate/AbstractRegistrate"
_BUILDER = "com/tterrag/registrate/builders/BlockEntityBuilder"
_FACTORY = "com/tterrag/registrate/builders/BlockEntityBuilder$BlockEntityFactory"
_BUILT = "__registrate_block_entity"
_ENTRY = "__registrate_block_entity_entry"


def _renderer_calls(cf, m) -> bool:
    from ...bytecode import instructions
    return m.code is not None and any(
        i.op in (0xB6, 0xB7, 0xB8, 0xB9) and getattr(i.arg, "owner", None) == _BUILDER
        and getattr(i.arg, "name", None) == "renderer" for i in instructions(cf, m.code))


def _hook(types, chains, entries: bool = False):
    """The builder reading: ``chains`` collects each registered chain's
    fields. With ``entries``, ``register()`` returns the chain's entry and
    the entry's ``get()`` its block entity type (see the module docstring);
    otherwise ``register()`` is unknown, as the renderer reading has it."""
    from ...blockcode import Lam, Obj, UNKNOWN

    def hook(owner, mname, desc, args, static):
        recv = None if static or not args else args[0]
        if isinstance(recv, Obj) and recv.cls == _BUILT:
            if mname == "renderer" and len(args) == 2:
                recv.fields["renderer"] = args[1]
                return [recv]
            if mname == "register" and len(args) == 1:
                chains.append(dict(recv.fields))
                return [Obj(_ENTRY, {"factory": recv.fields["factory"]})] if entries else [UNKNOWN]
            ret = desc.rsplit(")", 1)[-1]
            if ret.startswith("L") and _BUILDER in types.supers(ret[1:-1]):
                return [recv]  # the builder's fluent calls return the builder
            return [None] if ret == "V" else [UNKNOWN]
        if entries and isinstance(recv, Obj) and recv.cls == _ENTRY:
            if mname == "get" and len(args) == 1:
                typ = recv.fields.get("type")
                if typ is None:
                    factory = recv.fields["factory"]
                    typ = recv.fields["type"] = Obj("__betype", {})
                    typ.fields["factory"] = Lam(factory.handle, tuple(factory.captured) + (typ,),
                                                factory.itype, factory.iface)
                return [typ]
            ret = desc.rsplit(")", 1)[-1]
            return [None] if ret == "V" else [UNKNOWN]
        if mname == "blockEntity" and not static and _REGISTRATE in types.supers(owner) \
                and f"L{_FACTORY};" in desc:
            factories = [a for a in args[1:] if isinstance(a, Lam)]
            if len(factories) == 1:
                return [Obj(_BUILT, {"factory": factories[0], "renderer": None})]
        return None

    return hook


def renderer_bindings(classes) -> list:
    from ...blockcode import Lam, Machine, UNKNOWN, Unreadable, _arg_count
    from ...rendershape import Binding, _Types, _dotted, _one_class, _renderer_of
    names = [n for n in classes.names() if _BUILDER.encode() in (classes.raw(n) or b"")]
    if not names:
        return []
    types = _Types(classes)
    out: list = []
    for name in names:
        cf = classes.get(name)
        if cf is None:
            continue
        for m in cf.methods:
            if not _renderer_calls(cf, m):
                continue
            where = f"{_dotted(cf.name)}#{m.name}"
            label = f"{where} (Registrate's BlockEntityBuilder#renderer, bound in its registerRenderer)"
            chains: list = []
            machine = Machine(classes)
            machine.holders = True
            machine.call_hook = _hook(types, chains)
            n, _ = _arg_count(m.desc)
            try:
                machine.steps = 0
                if m.name == "<clinit>":
                    machine._clinit_done.add(cf.name)  # run below, once
                else:
                    machine.init_class(cf.name)
                machine.steps = 0
                machine.new_epoch()
                machine.run(cf, m, ([] if m.access & 0x0008 else [UNKNOWN]) + [UNKNOWN] * n)
            except Unreadable as exc:
                out.append(Binding(label, why=f"{where} can't be followed to the end ({exc})"))
            for chain in chains:
                sup = chain.get("renderer")
                if sup is None:
                    continue  # no renderer: nothing bound
                why, renderer, entity, provider = [], None, None, None
                if isinstance(sup, Lam):
                    machine.steps = 0
                    machine.new_epoch()
                    try:
                        made = machine.call_lambda(sup, [])
                    except Unreadable as exc:
                        made = []
                        why.append(f"the renderer supplier can't be followed ({exc})")
                    provider = made[0] if len(made) == 1 else None
                if provider is None and not why:
                    why.append("the renderer supplier isn't read")
                if provider is not None:
                    renderer, rwhy = _renderer_of(machine, types, provider)
                    if rwhy:
                        why.append(f"the renderer {rwhy}")
                machine.steps = 0
                machine.new_epoch()
                try:
                    entity, ewhy = _one_class(machine.call_lambda(chain["factory"], [UNKNOWN] * 3), types.is_be)
                except Unreadable as exc:
                    entity, ewhy = None, f"can't be followed ({exc})"
                if ewhy:
                    why.append(f"the factory {ewhy}")
                out.append(Binding(label, renderer and _dotted(renderer), entity and _dotted(entity),
                                   f"a chain in {label}: {'; '.join(why)}" if why else ""))
    return out


def _registering(classes) -> set:
    """The mod's own classes (not a library's) whose class initializer calls
    ``AbstractRegistrate#blockEntity`` with a ``BlockEntityFactory``
    (Create's ``AllBlockEntityTypes``): its entries are the ones a block's
    type method reads."""
    from ...bytecode import instructions
    out = set()
    for name in classes.names():
        if classes.is_library(name) or _FACTORY.encode() not in (classes.raw(name) or b""):
            continue
        cf = classes.get(name)
        m = cf and cf.method("<clinit>", "()V")
        if m is not None and m.code is not None and any(
                i.op in (0xB6, 0xB7, 0xB9) and getattr(i.arg, "name", None) == "blockEntity"
                and f"L{_FACTORY};" in (getattr(i.arg, "desc", None) or "") for i in instructions(cf, m.code)):
            out.add(name)
    return out


def block_entity_types(types):
    """(the Machine.call_hook reading Registrate's block entity chains and
    their entries' ``get()``, see the module docstring; the mod's classes
    that register through it, to run again under the hook), for
    :func:`portkit.rendershape.typed_entities`."""
    classes = types.classes
    if not any(_BUILDER.encode() in (classes.raw(n) or b"") for n in classes.names()):
        return None, set()
    return _hook(types, [], entries=True), _registering(classes)


ADAPTER = Adapter(
    name="registrate",
    library=True,
    renderer_bindings=renderer_bindings,
    block_entity_types=block_entity_types,
)
