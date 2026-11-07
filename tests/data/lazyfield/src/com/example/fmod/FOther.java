package com.example.fmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// The guard tests this block's field but fills another block's.
public class FOther extends FBlock {
  private FData data4;
  private FOther other;
  public FOther(Properties p) { super(p, true); }
  private FData getData4() {
    if (data4 == null) other.data4 = new FData(true);
    return data4;
  }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos pos, CollisionContext c) {
    return getData4().custom() ? getShape(s, g, pos, c) : Shapes.block();
  }
}
