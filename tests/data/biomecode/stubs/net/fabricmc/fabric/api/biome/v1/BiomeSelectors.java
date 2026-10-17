package net.fabricmc.fabric.api.biome.v1;
import java.util.function.Predicate;
import net.minecraft.tags.TagKey;
public final class BiomeSelectors {
    public static Predicate<BiomeSelectionContext> all() { return null; }
    public static Predicate<BiomeSelectionContext> foundInOverworld() { return null; }
    public static Predicate<BiomeSelectionContext> foundInTheNether() { return null; }
    public static Predicate<BiomeSelectionContext> foundInTheEnd() { return null; }
    public static Predicate<BiomeSelectionContext> tag(TagKey<?> tag) { return null; }
}
