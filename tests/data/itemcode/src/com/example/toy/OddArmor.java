package com.example.toy;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
public enum OddArmor implements ArmorMaterial {
    ODD(4);
    private final int factor;
    OddArmor(int factor) { this.factor = factor; }
    @Override public int getDurabilityForType(ArmorItem.Type type) { return type == ArmorItem.Type.HELMET ? 1 : this.factor; }
}
