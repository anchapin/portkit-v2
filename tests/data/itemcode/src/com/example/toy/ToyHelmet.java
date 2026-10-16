package com.example.toy;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
import net.minecraft.world.item.Item;
public class ToyHelmet extends ArmorItem {
    public static final ArmorItem.Type TYPE = ArmorItem.Type.HELMET;
    public ToyHelmet(ArmorMaterial material, Item.Properties properties) { super(material, TYPE, properties.stacksTo(1)); }
}
