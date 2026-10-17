package net.fabricmc.fabric.api.biome.v1;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.levelgen.GenerationStep;
public interface BiomeModificationContext {
    GenerationSettingsContext getGenerationSettings();
    interface GenerationSettingsContext {
        void addFeature(GenerationStep.Decoration step, ResourceKey<?> key);
        boolean removeFeature(GenerationStep.Decoration step, ResourceKey<?> key);
    }
}
