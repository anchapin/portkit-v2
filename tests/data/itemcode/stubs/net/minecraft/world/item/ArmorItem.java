package net.minecraft.world.item;
public class ArmorItem extends Item {
    public enum Type { HELMET, CHESTPLATE, LEGGINGS, BOOTS }
    public ArmorItem(ArmorMaterial material, Type type, Item.Properties properties) { super(properties); }
    public int getDefense() { return 0; }
}
