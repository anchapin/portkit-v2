package com.example.toy;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
public class ToyOddTexture extends ArmorItem {
    public ToyOddTexture(Item.Properties properties) { super(ToyPlate.PLATE, ArmorItem.Type.HELMET, properties); }
    public String getArmorTexture(ItemStack stack, Entity entity, EquipmentSlot slot, String type) {
        return slot == EquipmentSlot.HEAD ? "toy:textures/odd_head.png" : null;
    }
}
