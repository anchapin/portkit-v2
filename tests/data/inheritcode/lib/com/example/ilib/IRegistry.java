package com.example.ilib;
import java.util.IdentityHashMap;
import java.util.Map;
import net.minecraft.core.Registry;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.block.Block;
// Zeta's ZetaRegistry shape: names kept in an identity map, looked up with the vanilla registry as fallback.
public class IRegistry {
  public ILib z;
  private final Map<Object, ResourceLocation> internalNames = new IdentityHashMap<>();
  public void registerBlock(Block block, String name) {
    ResourceLocation rl = name.indexOf(':') == -1 ? ResourceLocation.fromNamespaceAndPath(z.modid, name) : ResourceLocation.parse(name);
    internalNames.put(block, rl);
  }
  public <T> ResourceLocation getRegistryName(T obj, Registry<T> registry) {
    ResourceLocation rl = internalNames.get(obj);
    return rl == null ? registry.getKey(obj) : rl;
  }
}
