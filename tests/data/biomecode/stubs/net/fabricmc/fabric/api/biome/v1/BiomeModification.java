package net.fabricmc.fabric.api.biome.v1;
import java.util.function.BiConsumer;
import java.util.function.Predicate;
public class BiomeModification {
    public BiomeModification add(ModificationPhase phase, Predicate<BiomeSelectionContext> selector,
                                 BiConsumer<BiomeSelectionContext, BiomeModificationContext> modifier) { return this; }
}
