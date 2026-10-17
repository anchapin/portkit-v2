package net.fabricmc.fabric.api.biome.v1;
import java.util.function.Predicate;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.levelgen.GenerationStep;
public final class BiomeModifications {
    public static void addFeature(Predicate<BiomeSelectionContext> selector, GenerationStep.Decoration step,
                                  ResourceKey<?> key) {}
    public static BiomeModification create(ResourceLocation id) { return null; }
}
