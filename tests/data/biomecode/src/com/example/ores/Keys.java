package com.example.ores;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.tags.TagKey;
public class Keys {
    public static ResourceLocation id(String path) { return ResourceLocation.fromNamespaceAndPath("exampleores", path); }
    public static ResourceKey<Object> placed(String path) { return ResourceKey.create(Registries.PLACED_FEATURE, id(path)); }
    public static TagKey<Object> biomes(String path) { return TagKey.create(Registries.BIOME, id(path)); }
}
