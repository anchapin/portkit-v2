package net.minecraft.world.level;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.FluidState;
public class Level implements BlockGetter { public boolean isClientSide;
  public FluidState getFluidState(BlockPos p) { return null; }
  public BlockState getBlockState(BlockPos p) { return null; }
  public boolean isClientSide() { return isClientSide; }
  public boolean setBlock(BlockPos p, BlockState s, int f) { return true; }
  public boolean setBlockAndUpdate(BlockPos p, BlockState s) { return true; }
  public boolean hasNeighborSignal(BlockPos p) { return false; }
  public net.minecraft.world.level.border.WorldBorder getWorldBorder() { return null; }
  public void levelEvent(net.minecraft.world.entity.player.Player p, int e, BlockPos at, int d) {}
  public net.minecraft.world.level.block.entity.BlockEntity getBlockEntity(BlockPos p) { return null; } }
