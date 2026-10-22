package net.minecraft.client.renderer.blockentity;
import net.minecraft.world.level.block.entity.BlockEntity;
public interface BlockEntityRendererProvider<T extends BlockEntity> {
  BlockEntityRenderer<T> create(Context c);
  class Context { } }
