package com.example.toy;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.Item;
public class ToyBranchArmor extends ArmorItem {
    public ToyBranchArmor(boolean heavy, Item.Properties properties) { super(heavy ? ToyPlate.HEAVY : ToyPlate.PLATE, ArmorItem.Type.LEGGINGS, properties); }
}
