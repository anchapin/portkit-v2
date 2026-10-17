package com.example.ores;
import net.fabricmc.fabric.api.biome.v1.BiomeModifications;
import net.fabricmc.fabric.api.biome.v1.BiomeSelectors;
import net.minecraft.world.level.levelgen.GenerationStep;
/** Calls the biome API, but no entrypoint reaches it. */
public class Unused {
    public static void neverCalled() {
        BiomeModifications.addFeature(BiomeSelectors.foundInOverworld(), GenerationStep.Decoration.UNDERGROUND_ORES,
                Keys.placed("ore_unused"));
    }
}
