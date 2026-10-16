package com.example.toy;
import java.util.Locale;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
// Create's BaseArmorItem shape: a texture location field and Forge's own format in getArmorTexture.
public class ToyTexturedArmor extends ArmorItem {
    protected final ResourceLocation textureLoc;
    public ToyTexturedArmor(ArmorMaterial material, ArmorItem.Type type, Item.Properties properties, ResourceLocation textureLoc) {
        super(material, type, properties.stacksTo(1));
        this.textureLoc = textureLoc;
    }
    public String getArmorTexture(ItemStack stack, Entity entity, EquipmentSlot slot, String type) {
        return String.format(Locale.ROOT, "%s:textures/models/armor/%s_layer_%d%s.png", textureLoc.getNamespace(),
                textureLoc.getPath(), slot == EquipmentSlot.LEGS ? 2 : 1,
                type == null ? "" : String.format(Locale.ROOT, "_%s", type));
    }
}
