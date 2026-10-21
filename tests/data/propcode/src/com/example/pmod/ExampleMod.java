package com.example.pmod;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.Item;
public class ExampleMod {
    public static final String MODID = "examplemod";
    public static Item compass;
    public static Item gauge;
    public static Item watch;
    public static Item pouch;
    // The mod's own helper: its namespace in front of a path.
    public static ResourceLocation id(String path) { return ResourceLocation.fromNamespaceAndPath(MODID, path); }
    // A helper of the helper.
    public static ResourceLocation res(String path) { return id(path); }
}
