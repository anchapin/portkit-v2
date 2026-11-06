"""#296: ``Registry#getKey`` for objects the mod registers itself
(``blockcode.Machine._holder_call`` / ``_registry_key``): a modelled
``DeferredRegister`` files each holder's value under ``namespace:name``,
the same call run again on unknown arguments takes the key its real call
filed, resource locations key maps by namespace and path, and fastutil's
``Object2FloatArrayMap`` answers ``getFloat`` with its default return value.
Classes are made here, not read from any jar."""
from __future__ import annotations

from portkit import blockcode
from portkit.bytecode import ClassIndex, Handle, Ref

_REG = "net/neoforged/neoforge/registries/DeferredRegister"
_REGISTER = "(Ljava/lang/String;Ljava/util/function/Supplier;)Lnet/neoforged/neoforge/registries/DeferredHolder;"
_CREATE = "(Lnet/minecraft/core/Registry;Ljava/lang/String;)Lnet/neoforged/neoforge/registries/DeferredRegister;"
_BIR = "net/minecraft/core/registries/BuiltInRegistries"
_TYPE = "net/minecraft/world/level/block/entity/BlockEntityType"
_GET_KEY = "(Ljava/lang/Object;)Lnet/minecraft/resources/ResourceLocation;"
_F2 = "it/unimi/dsi/fastutil/objects/Object2FloatArrayMap"


def _lam(name: str = "lambda$0") -> blockcode.Lam:
    return blockcode.Lam(Handle(6, Ref("a/Reg", name, f"()L{_TYPE};")))


def _machine(monkeypatch, made):
    machine = blockcode.Machine(ClassIndex({}))
    machine.holders = machine.entity_types = True
    monkeypatch.setattr(machine, "call_lambda", lambda lam, args: [made[lam.handle.ref.name]])
    return machine


def _register(machine, recv, name, lam, site=("a/Reg", "init", "()V"), pc=7):
    machine._methods, machine._frame = [site], blockcode.Frame(pc, [], [])
    machine._register_recv = recv
    try:
        return machine._holder_call(_REG, "register", _REGISTER, blockcode.UNKNOWN, [name, lam], False)
    finally:
        machine._register_recv = None


def _get(machine, holder):
    return machine._holder_call("net/neoforged/neoforge/registries/DeferredHolder", "get", "()Ljava/lang/Object;",
                                holder, [], False)


def _key(machine, registry, obj):
    return machine._registry_key("net/minecraft/core/Registry", "getKey", _GET_KEY,
                                 blockcode.Const(_BIR, registry), [obj], False)


def test_deferred_register_files_holder_values_under_its_namespace(monkeypatch):
    kind = blockcode.Obj(_TYPE)
    machine = _machine(monkeypatch, {"lambda$0": kind})
    (register,) = machine._holder_call(_REG, "create", _CREATE, None,
                                       [blockcode.Const(_BIR, "BLOCK_ENTITY_TYPE"), "examplemod"], True)
    assert register.cls == "__register"
    (holder,) = _register(machine, register, "lamp", _lam())
    assert holder.fields["key"] == ("BLOCK_ENTITY_TYPE", "examplemod:lamp")
    assert _get(machine, holder) == [kind]
    assert _key(machine, "BLOCK_ENTITY_TYPE", kind) == [blockcode.RL("examplemod:lamp", True)]
    # Another registry's getKey, or an object nothing filed, isn't answered.
    assert _key(machine, "ITEM", kind) is blockcode._NOT_HANDLED
    assert _key(machine, "BLOCK_ENTITY_TYPE", blockcode.Obj(_TYPE)) is blockcode._NOT_HANDLED


def test_a_register_whose_namespace_or_registry_is_unknown_is_not_modelled():
    machine = blockcode.Machine(ClassIndex({}))
    machine.holders = True
    reg = blockcode.Const(_BIR, "BLOCK_ENTITY_TYPE")
    assert machine._holder_call(_REG, "create", _CREATE, None, [reg, blockcode.UNKNOWN], True) \
        is blockcode._NOT_HANDLED
    assert machine._holder_call(_REG, "create", _CREATE, None, [blockcode.UNKNOWN, "examplemod"], True) \
        is blockcode._NOT_HANDLED


def test_a_rerun_on_unknown_arguments_takes_the_key_its_call_site_filed(monkeypatch):
    first, again = blockcode.Obj(_TYPE), blockcode.Obj(_TYPE)
    machine = _machine(monkeypatch, {"lambda$0": first})
    register = blockcode.Obj("__register", {"registry": "BLOCK_ENTITY_TYPE", "namespace": "examplemod"})
    _register(machine, register, "lv_conn", _lam())
    (rerun,) = _register(machine, None, "lv_conn", _lam())
    assert "key" not in rerun.fields
    monkeypatch.setattr(machine, "call_lambda", lambda lam, args: [again])
    _get(machine, rerun)
    assert _key(machine, "BLOCK_ENTITY_TYPE", again) == [blockcode.RL("examplemod:lv_conn", True)]
    # A call site its real calls filed under two keys gives a rerun none.
    other = blockcode.Obj("__register", {"registry": "BLOCK_ENTITY_TYPE", "namespace": "othermod"})
    _register(machine, other, "lv_conn", _lam())
    third = blockcode.Obj(_TYPE)
    monkeypatch.setattr(machine, "call_lambda", lambda lam, args: [third])
    _get(machine, rerun)
    assert _key(machine, "BLOCK_ENTITY_TYPE", third) is blockcode._NOT_HANDLED
    # Nor does a different call site.
    (elsewhere,) = _register(machine, None, "lv_conn", _lam(), pc=99)
    fourth = blockcode.Obj(_TYPE)
    monkeypatch.setattr(machine, "call_lambda", lambda lam, args: [fourth])
    _get(machine, elsewhere)
    assert _key(machine, "BLOCK_ENTITY_TYPE", fourth) is blockcode._NOT_HANDLED


def test_an_object_filed_under_two_keys_has_none():
    machine = blockcode.Machine(ClassIndex({}))
    obj = blockcode.Obj(_TYPE)
    machine._file_key(obj, "BLOCK_ENTITY_TYPE", "a:x")
    machine._file_key(obj, "BLOCK_ENTITY_TYPE", "a:x")
    assert _key(machine, "BLOCK_ENTITY_TYPE", obj) == [blockcode.RL("a:x", True)]
    machine._file_key(obj, "BLOCK_ENTITY_TYPE", "a:y")
    assert _key(machine, "BLOCK_ENTITY_TYPE", obj) is blockcode._NOT_HANDLED


def test_fabric_registry_register_files_a_namespaced_id():
    machine = blockcode.Machine(ClassIndex({}))
    machine.holders = True
    obj = blockcode.Obj(_TYPE)
    reg = blockcode.Const(_BIR, "BLOCK_ENTITY_TYPE")
    desc = "(Lnet/minecraft/core/Registry;Lnet/minecraft/resources/ResourceLocation;Ljava/lang/Object;)Ljava/lang/Object;"
    assert machine._holder_call("net/minecraft/core/Registry", "register", desc, None,
                                [reg, blockcode.RL("examplemod:lamp"), obj], True) == [obj]
    assert _key(machine, "BLOCK_ENTITY_TYPE", obj) == [blockcode.RL("examplemod:lamp", True)]
    # A namespace that isn't known files nothing.
    other = blockcode.Obj(_TYPE)
    machine._holder_call("net/minecraft/core/Registry", "register", desc, None,
                         [reg, blockcode.RL(blockcode.Tail("lamp")), other], True)
    assert _key(machine, "BLOCK_ENTITY_TYPE", other) is blockcode._NOT_HANDLED


def test_modelled_register_is_unknown_to_every_other_call():
    machine = blockcode.Machine(ClassIndex({}))
    register = blockcode.Obj("__register", {"registry": "BLOCK", "namespace": "examplemod"})
    seen = []
    machine.call_hook = lambda owner, name, desc, args, static: seen.append(args[0]) or [None]
    machine.call(_REG, "register", "(Lnet/neoforged/bus/api/IEventBus;)V", [register, blockcode.UNKNOWN])
    assert seen == [blockcode.UNKNOWN]


def test_resource_locations_key_maps_by_namespace_and_path():
    machine = blockcode.Machine(ClassIndex({}))
    m = blockcode.MapV({})
    put = "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;"
    get = "(Ljava/lang/Object;)Ljava/lang/Object;"
    machine._map_call(m, "put", put, [blockcode.RL("examplemod:lv_conn"), "spec"])
    # getKey's mark takes no part in equality.
    assert machine._map_call(m, "get", get, [blockcode.RL("examplemod:lv_conn", True)]) == ["spec"]
    assert machine._map_call(m, "get", get, [blockcode.RL("examplemod:hv_conn", True)]) == [None]
    # A location whose namespace isn't known isn't known to miss.
    assert machine._map_call(m, "get", get, [blockcode.RL(blockcode.Tail("lv_conn"))]) == [blockcode.UNKNOWN]
    # A bare path is in "minecraft".
    machine._map_call(m, "put", put, [blockcode.RL("stone"), "rock"])
    assert machine._map_call(m, "get", get, [blockcode.RL("minecraft:stone")]) == ["rock"]


def test_fastutil_float_map_answers_its_default_return_value():
    machine = blockcode.Machine(ClassIndex({}))
    m = machine._new(_F2)
    assert m.kind == "float"
    key = blockcode.DfuPair("HV", 0)
    assert machine._map_call(m, "put", "(Ljava/lang/Object;F)F", [key, 0.75]) == [0.0]
    assert machine._map_call(m, "defaultReturnValue", "(F)V", [0.5]) == [None]
    assert machine._map_call(m, "getFloat", "(Ljava/lang/Object;)F", [blockcode.DfuPair("HV", 0)]) == [0.75]
    assert machine._map_call(m, "getFloat", "(Ljava/lang/Object;)F", [blockcode.DfuPair("MV", 1)]) == [0.5]
    assert machine._map_call(m, "put", "(Ljava/lang/Object;F)F", [key, 0.875]) == [0.75]
    # A key that doesn't compare exactly, or a call outside the model,
    # leaves the map unknown.
    assert machine._map_call(m, "getFloat", "(Ljava/lang/Object;)F", [blockcode.UNKNOWN]) == [blockcode.UNKNOWN]
    assert machine._map_call(m, "removeFloat", "(Ljava/lang/Object;)F", [key]) == [blockcode.UNKNOWN]
    assert machine._map_call(m, "getFloat", "(Ljava/lang/Object;)F", [key]) == [blockcode.UNKNOWN]
