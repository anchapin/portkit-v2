package net.minecraft.world.level;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.FluidState;
public class Level implements BlockGetter { public boolean isClientSide;
  public FluidState getFluidState(BlockPos p) { return null; }
  public boolean isClientSide() { return isClientSide; }
  public boolean setBlock(BlockPos p, BlockState s, int f) { return true; }
  public boolean hasNeighborSignal(BlockPos p) { return false; } }
