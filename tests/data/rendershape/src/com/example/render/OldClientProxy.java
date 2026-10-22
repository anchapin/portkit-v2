package com.example.render;
import net.minecraftforge.fml.client.registry.ClientRegistry;
// 1.12: the block entity class and a renderer object.
public class OldClientProxy {
  public void init() { ClientRegistry.bindTileEntitySpecialRenderer(OldChestTile.class, new OldChestRenderer()); }
}
