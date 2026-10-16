package com.example.toy;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.Item;
public class ToyTexturedHelmet extends ToyTexturedArmor {
    public ToyTexturedHelmet(Item.Properties properties) { super(ToyPlate.PLATE, ArmorItem.Type.HELMET, properties, ToyLooks.id("plate_look")); }
}
