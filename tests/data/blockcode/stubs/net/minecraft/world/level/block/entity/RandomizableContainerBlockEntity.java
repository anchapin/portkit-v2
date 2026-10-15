package net.minecraft.world.level.block.entity;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.block.state.BlockState;
public abstract class RandomizableContainerBlockEntity extends BaseContainerBlockEntity {
  protected RandomizableContainerBlockEntity(BlockEntityType<?> t, BlockPos p, BlockState s) { super(t, p, s); } }
