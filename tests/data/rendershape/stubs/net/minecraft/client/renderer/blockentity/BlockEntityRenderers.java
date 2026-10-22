package net.minecraft.client.renderer.blockentity;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityType;
public class BlockEntityRenderers {
  public static <T extends BlockEntity> void register(BlockEntityType<? extends T> t, BlockEntityRendererProvider<T> p) { } }
