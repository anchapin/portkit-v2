package net.minecraft.world.level.block.entity;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.Level; import net.minecraft.world.level.block.state.BlockState;
public class BlockEntity { protected Level level; protected BlockPos worldPosition;
  public BlockEntity(BlockEntityType<?> t, BlockPos p, BlockState s) {}
  public BlockState getBlockState() { return null; }
  public Level getLevel() { return level; } }
