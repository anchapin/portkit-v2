package net.minecraft.world.item;
public interface ArmorMaterial {
    int getDurabilityForType(ArmorItem.Type type);
    default int getDefenseForType(ArmorItem.Type type) { return 0; }
    default int getEnchantmentValue() { return 0; }
    default float getToughness() { return 0.0F; }
    default float getKnockbackResistance() { return 0.0F; }
}
