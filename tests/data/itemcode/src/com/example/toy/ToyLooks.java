package com.example.toy;
import java.util.List;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ArmorMaterial;
// 1.21.1-style layer lists and a mod's own id helper (Mythic Metals' RegistryHelper.id shape).
public class ToyLooks {
    public static final Object PLAIN = List.of(layer("plate"));
    public static final Object SUFFIXED = List.of(new ArmorMaterial.Layer(id("plate"), "_glow", false));
    public static final Object DYED = List.of(new ArmorMaterial.Layer(id("cloth"), "", true));
    public static final Object TWO = List.of(layer("cloth"), layer("cloth_overlay"));
    public static ResourceLocation id(String path) { return ResourceLocation.fromNamespaceAndPath("toy", path); }
    public static ArmorMaterial.Layer layer(String name) { return new ArmorMaterial.Layer(id(name)); }
}
