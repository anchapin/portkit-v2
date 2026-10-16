package com.example.toy;
import java.util.function.Function;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.Item;
public class ToyArmorItems {
    public static final Object PLATE_HELMET = register("plate_helmet", p -> new ToyPlateItem(ArmorItem.Type.HELMET, p));
    public static final Object HEAVY_CHESTPLATE = register("heavy_chestplate", p -> new ToyPlateItem(ToyPlate.HEAVY, ArmorItem.Type.CHESTPLATE, p));
    public static final Object HEAVY_BOOTS = register("heavy_boots", p -> new ToyBoots(ToyPlate.HEAVY, p));
    public static final Object CODE_CHESTPLATE = register("code_chestplate", p -> new ToyCodeArmor(p));
    public static final Object BRANCH_LEGGINGS = register("branch_leggings", p -> new ToyBranchArmor(true, p));
    public static final Object TOUGH_HELMET = register("tough_helmet", p -> new ToyPlateItem(ArmorItem.Type.HELMET, p.durability(5)));
    public static final Object TEXTURED_HELMET = register("textured_helmet", p -> new ToyTexturedHelmet(p));
    public static final Object ODD_HELMET = register("odd_helmet", p -> new ToyOddTexture(p));
    public static final Object MODEL_HELMET = register("model_helmet", p -> new ToyModelHelmet(p));
    public static final Object OVERLAY_HELMET = register("overlay_helmet", p -> new ToyOverlayHelmet(p));
    static Object register(String name, Function<Item.Properties, Item> factory) { return factory.apply(new Item.Properties()); }
}
