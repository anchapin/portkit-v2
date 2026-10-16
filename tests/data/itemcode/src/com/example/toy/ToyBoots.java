package com.example.toy;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
import net.minecraft.world.item.Item;
public class ToyBoots extends ToyPlateItem {
    public static final ArmorItem.Type TYPE = ArmorItem.Type.BOOTS;
    public ToyBoots(ArmorMaterial material, Item.Properties properties) { super(material, TYPE, properties); }
}
