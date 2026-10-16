package com.example.toy;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
public enum ToyArmor implements ArmorMaterial {
    BRONZE("bronze", 9), SILVER("silver", 20);
    private static final int[] MAX_DAMAGE_ARRAY = new int[]{11, 16, 15, 13};
    private final String name;
    private final int factor;
    ToyArmor(String name, int factor) { this.name = name; this.factor = factor; }
    @Override public int getDurabilityForType(ArmorItem.Type type) { return MAX_DAMAGE_ARRAY[type.ordinal()] * this.factor; }
}
