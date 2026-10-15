package net.minecraftforge.registries;
import java.util.function.Supplier;
public class DeferredRegister<T> {
    public static <B> DeferredRegister<B> create(Object registry, String modid) { return null; }
    public <I extends T> RegistryObject<I> register(String name, Supplier<? extends I> sup) { return null; }
}
