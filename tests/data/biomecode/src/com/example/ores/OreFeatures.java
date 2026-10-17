package com.example.ores;
import net.fabricmc.fabric.api.biome.v1.BiomeModifications;
import net.fabricmc.fabric.api.biome.v1.BiomeSelectors;
import net.fabricmc.fabric.api.biome.v1.ModificationPhase;
import net.minecraft.resources.ResourceKey;
import net.minecraft.tags.TagKey;
import net.minecraft.world.level.levelgen.GenerationStep;
public class OreFeatures {
    public static final ResourceKey<Object> SILVER = Keys.placed("ore_silver");
    public static final ResourceKey<Object> TIN = Keys.placed("ore_tin");
    public static final ResourceKey<Object> DEEP_TIN = Keys.placed("ore_deep_tin");
    public static final ResourceKey<Object> RUBY = Keys.placed("ore_ruby");
    public static final ResourceKey<Object> NETHER = Keys.placed("ore_nether");
    public static final ResourceKey<Object> END = Keys.placed("ore_end");
    public static final ResourceKey<Object> GONE = Keys.placed("ore_gone");
    public static final ResourceKey<Object> ODD = Keys.placed("ore_odd");
    public static final ResourceKey<Object> LUCKY = Keys.placed("ore_lucky");
    public static final TagKey<Object> SILVER_BIOMES = Keys.biomes("silver_biomes");
    public static final TagKey<Object> TIN_BIOMES = Keys.biomes("tin_biomes");
    public static int luck;

    public static void init() {
        if (ExampleMod.CONFIG.silver()) {
            OreHelper.ore(SILVER, SILVER_BIOMES);
        }
        if (ExampleMod.CONFIG.tin()) {
            OreHelper.ore(TIN, TIN_BIOMES);
            OreHelper.ore(DEEP_TIN, TIN_BIOMES);
        }
        if (!ExampleMod.CONFIG.ruby()) {
            OreHelper.ore(RUBY, SILVER_BIOMES);
        }
        BiomeModifications.addFeature(BiomeSelectors.foundInTheNether(), GenerationStep.Decoration.UNDERGROUND_ORES, NETHER);
        BiomeModifications.create(Keys.id("end_ores")).add(ModificationPhase.ADDITIONS, BiomeSelectors.foundInTheEnd(),
                (selection, context) -> context.getGenerationSettings().addFeature(
                        GenerationStep.Decoration.UNDERGROUND_DECORATION, END));
        BiomeModifications.create(Keys.id("cleanup")).add(ModificationPhase.REMOVALS, BiomeSelectors.all(),
                (selection, context) -> context.getGenerationSettings().removeFeature(
                        GenerationStep.Decoration.UNDERGROUND_ORES, GONE));
        BiomeModifications.addFeature(BiomeSelectors.foundInOverworld().and(BiomeSelectors.tag(TIN_BIOMES)),
                GenerationStep.Decoration.UNDERGROUND_ORES, ODD);
        if (luck > 3) {
            BiomeModifications.addFeature(BiomeSelectors.foundInOverworld(), GenerationStep.Decoration.UNDERGROUND_ORES, LUCKY);
        }
    }
}
