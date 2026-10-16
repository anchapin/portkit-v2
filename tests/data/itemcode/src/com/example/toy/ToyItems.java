package com.example.toy;
import java.util.function.Function;
import net.minecraft.world.item.Item;
public class ToyItems {
    public static final Object HELMET = register("toy_helmet", p -> new ToyHelmet(ToyArmor.BRONZE, p));
    public static final Object BLADE = register("toy_blade", p -> new ToyBlade(ToyTiers.SILVER, p));
    public static final Object PLAIN = new Item(new Item.Properties());
    static Object register(String name, Function<Item.Properties, Item> factory) { return factory.apply(new Item.Properties()); }
}
