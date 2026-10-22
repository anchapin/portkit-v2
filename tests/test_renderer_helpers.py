"""#362: renderer bindings made through helpers the #355 reader didn't follow.

A method reference to a registration call handed to a helper, Stream#map /
Stream#toArray keeping the element count, a provider object of the mod's own
class, java.util.ServiceLoader read from META-INF/services, and the
Registrate library adapter's builder reading.
"""
from __future__ import annotations

from portkit import adapters, rendershape
from portkit.blockcode import UNKNOWN, Arr, ClassLit, Lam, Machine, Obj, Strm
from portkit.bytecode import ClassIndex, Handle, Indy, Insn, Ref

_RR = "net/minecraftforge/client/event/EntityRenderersEvent$RegisterRenderers"


def _insn(op, arg):
    return Insn(0, op, arg)


def test_a_method_reference_to_a_registration_call_is_a_site():
    ref = Ref(_RR, "registerBlockEntityRenderer", "(Lx;Ly;)V")
    meta = Handle(6, Ref("java/lang/invoke/LambdaMetafactory", "metafactory", "()V"))
    indy = Indy("register", "(L%s;)Lh/BERConsumer;" % _RR, meta, (("methodtype", "()V"), Handle(5, ref)))
    assert rendershape._is_bind(_insn(0xBA, indy))
    assert rendershape._is_bind(_insn(0xB6, ref))
    other = Indy("register", "()V", meta, (("methodtype", "()V"), Handle(5, Ref("a/B", "register", "()V"))))
    assert not rendershape._is_bind(_insn(0xBA, other))


def test_stream_map_keeps_the_count_and_to_array_builds_the_array():
    m = Machine(ClassIndex({}))
    lam = UNKNOWN  # a function the run can't follow
    mapped = m._stream(Strm((Obj("a/A"), Obj("a/A"))), "map", "(Ljava/util/function/Function;)"
                       "Ljava/util/stream/Stream;", [lam])
    assert len(mapped) == 1 and isinstance(mapped[0], Strm) and len(mapped[0].items) == 2
    arr = m._stream(mapped[0], "toArray", "(Ljava/util/function/IntFunction;)[Ljava/lang/Object;", [UNKNOWN])
    assert isinstance(arr[0], Arr) and len(arr[0].items) == 2


def test_service_files_are_read_as_service_loader_does():
    index = ClassIndex({"a/Service": b"", "a/Impl": b""})
    index.add_services({"META-INF/services/a.Service": b"# comment\n a.Impl  # trailing\n\na.Impl\nb.Other\n"})
    assert index.services["a.Service"] == ["a/Impl", "b/Other"]


def test_service_loader_of_another_jars_service_is_unknown():
    index = ClassIndex({})
    index.add_services({"META-INF/services/x.Service": b"x.Impl\n"})
    m = Machine(index)
    got = m._service_call("java/util/ServiceLoader", "load", "(Ljava/lang/Class;)Ljava/util/ServiceLoader;",
                          None, [ClassLit("x/Service")], True)
    assert got == [UNKNOWN]


def test_registrate_is_a_library_adapter_with_a_renderer_hook():
    found = [a for a in adapters.ADAPTERS if a.name == "registrate"]
    assert found and found[0].library and found[0].renderer_bindings is not None
    assert adapters.check() == []
    # A jar that never names Registrate's builder gets nothing from it.
    assert found[0].renderer_bindings(ClassIndex({})) == []
