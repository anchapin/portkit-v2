package com.example.render;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraftforge.client.event.EntityRenderersEvent;
// A helper making the call with what its caller hands it, and the handler calling it.
public class ClientHelpers {
  static <T extends BlockEntity> void bind(EntityRenderersEvent.RegisterRenderers e, BlockEntityType<T> type,
                                           BlockEntityRendererProvider<T> provider) {
    e.registerBlockEntityRenderer(type, provider);
  }
  public static void onRegister(EntityRenderersEvent.RegisterRenderers e) { bind(e, Types.LAMP, LampRenderer::new); }
}
