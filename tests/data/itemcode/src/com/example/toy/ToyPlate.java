package com.example.toy;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
public enum ToyPlate implements ArmorMaterial {
    PLATE("plate", 15, new int[]{2, 5, 4, 1}, 12, 1.5F, 0.0F),
    HEAVY("heavy", 30, new int[]{3, 8, 6, 3}, 9, 2.0F, 0.1F);
    private static final int[] MAX_DAMAGE_ARRAY = new int[]{11, 16, 15, 13};
    private final String name;
    private final int factor;
    private final int[] defense;
    private final int enchantability;
    private final float toughness;
    private final float knockback;
    ToyPlate(String name, int factor, int[] defense, int enchantability, float toughness, float knockback) {
        this.name = name; this.factor = factor; this.defense = defense;
        this.enchantability = enchantability; this.toughness = toughness; this.knockback = knockback;
    }
    @Override public int getDurabilityForType(ArmorItem.Type type) { return MAX_DAMAGE_ARRAY[type.ordinal()] * this.factor; }
    @Override public int getDefenseForType(ArmorItem.Type type) { return this.defense[type.ordinal()]; }
    @Override public int getEnchantmentValue() { return this.enchantability; }
    @Override public float getToughness() { return this.toughness; }
    @Override public float getKnockbackResistance() { return this.knockback; }
}
