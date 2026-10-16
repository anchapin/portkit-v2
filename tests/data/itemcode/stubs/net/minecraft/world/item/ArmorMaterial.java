package net.minecraft.world.item;
import net.minecraft.resources.ResourceLocation;
public interface ArmorMaterial {
    int getDurabilityForType(ArmorItem.Type type);
    default int getDefenseForType(ArmorItem.Type type) { return 0; }
    default int getEnchantmentValue() { return 0; }
    default float getToughness() { return 0.0F; }
    default float getKnockbackResistance() { return 0.0F; }
    default String getName() { return ""; }
    // 1.21.1's ArmorMaterial.Layer, nested here so one stub serves both shapes.
    class Layer {
        public Layer(ResourceLocation id) { this(id, "", false); }
        public Layer(ResourceLocation id, String suffix, boolean dyeable) {}
    }
}
