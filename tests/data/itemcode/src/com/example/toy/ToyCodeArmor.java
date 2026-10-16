package com.example.toy;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.Item;
public class ToyCodeArmor extends ToyPlateItem {
    public ToyCodeArmor(Item.Properties properties) { super(ArmorItem.Type.CHESTPLATE, properties); }
    @Override public int getDefense() { return 99; }
}
