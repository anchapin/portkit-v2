package com.tterrag.registrate.builders;
import com.tterrag.registrate.util.entry.BlockEntityEntry;
import java.util.function.Function; import java.util.function.Supplier;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityType; import net.minecraft.world.level.block.state.BlockState;
public class BlockEntityBuilder<T extends BlockEntity, P> {
  public interface BlockEntityFactory<T extends BlockEntity> { T create(BlockEntityType<T> type, BlockPos pos, BlockState state); }
  public BlockEntityBuilder<T, P> validBlocks(Object... blocks) { return this; }
  public BlockEntityBuilder<T, P> renderer(Supplier<Function<BlockEntityRendererProvider.Context, BlockEntityRenderer<? super T>>> r) { return this; }
  public BlockEntityEntry<T> register() { return null; } }
