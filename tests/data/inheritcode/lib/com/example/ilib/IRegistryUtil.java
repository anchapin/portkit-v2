package com.example.ilib;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.block.Block;
// Zeta's RegistryUtil#inherit shape: "<modid>:" + a format given the parent's registered path.
public class IRegistryUtil {
  public ILib z;
  public String inherit(IVariantBlock parent, String format) { return inherit(parent.getBlock(), format); }
  public String inherit(Block parent, String format) {
    ResourceLocation rl = z.registry.getRegistryName(parent, BuiltInRegistries.BLOCK);
    if (rl == null) return null;
    return String.format(String.format("%s:%s", z.modid, format), rl.getPath());
  }
}
