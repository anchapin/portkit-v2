package com.example.render;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderers;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraftforge.client.event.EntityRenderersEvent;
// The client's renderer registrations, as a loader event handler makes them.
public class ClientSetup {
  public static void registerRenderers(EntityRenderersEvent.RegisterRenderers event) {
    event.registerBlockEntityRenderer(Types.POOL, PoolRenderer::new);
    event.registerBlockEntityRenderer(Types.SPINNER, c -> new SpinnerRenderer());
    BlockEntityRenderers.register(Types.BEARING, KineticRenderer::new);
  }
  // The type comes from the caller: the call can't be read on its own.
  public static void later(EntityRenderersEvent.RegisterRenderers event, BlockEntityType<ShaftBlockEntity> type) {
    event.registerBlockEntityRenderer(type, KineticRenderer::new);
  }
}
