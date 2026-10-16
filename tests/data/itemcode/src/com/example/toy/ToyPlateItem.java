package com.example.toy;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
import net.minecraft.world.item.Item;
public class ToyPlateItem extends ArmorItem {
    public ToyPlateItem(ArmorMaterial material, ArmorItem.Type type, Item.Properties properties) { super(material, type, properties.stacksTo(1)); }
    public ToyPlateItem(ArmorItem.Type type, Item.Properties properties) { this(ToyPlate.PLATE, type, properties); }
}
