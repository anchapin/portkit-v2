package net.neoforged.neoforge.registries;
import java.util.function.Supplier;
public class DeferredRegister<T> {
    public <I extends T> Object register(String name, Supplier<? extends I> sup) { return null; }
}
