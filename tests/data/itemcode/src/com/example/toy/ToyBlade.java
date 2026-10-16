package com.example.toy;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.SwordItem;
import net.minecraft.world.item.Tier;
public class ToyBlade extends SwordItem {
    public ToyBlade(Tier tier, Item.Properties properties) { super(tier, properties.durability(99)); }
}
