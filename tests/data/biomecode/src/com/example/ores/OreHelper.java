package com.example.ores;
import net.fabricmc.fabric.api.biome.v1.BiomeModifications;
import net.fabricmc.fabric.api.biome.v1.BiomeSelectors;
import net.minecraft.resources.ResourceKey;
import net.minecraft.tags.TagKey;
import net.minecraft.world.level.levelgen.GenerationStep;
public class OreHelper {
    public static void ore(ResourceKey<Object> key, TagKey<Object> tag) {
        BiomeModifications.addFeature(BiomeSelectors.tag(tag), GenerationStep.Decoration.UNDERGROUND_ORES, key);
    }
}
