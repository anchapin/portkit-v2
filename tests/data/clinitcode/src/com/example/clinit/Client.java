package com.example.clinit;
import java.util.function.Supplier;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraftforge.client.event.EntityRenderersEvent;
// One caching provider bound to several types read from their holders.
public class Client {
  public static void onRegister(EntityRenderersEvent.RegisterRenderers e) {
    bindAll(e, BinRenderer::new, Types.BIN, Types.FORKED); }
  @SuppressWarnings("unchecked")
  static <T extends BlockEntity> void bindAll(EntityRenderersEvent.RegisterRenderers e,
                                              BlockEntityRendererProvider<T> p, Object... holders) {
    BlockEntityRendererProvider<T> cached = new Caching<>(p);
    for (Object h : holders) e.registerBlockEntityRenderer(((Supplier<BlockEntityType<T>>) h).get(), cached); } }
