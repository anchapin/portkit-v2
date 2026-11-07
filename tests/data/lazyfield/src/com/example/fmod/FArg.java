package com.example.fmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// The fill reads an argument: a set field holds the first caller's value.
public class FArg extends FBlock {
  private FData data3;
  public FArg(Properties p) { super(p, true); }
  private FData getData3(boolean b) {
    if (data3 == null) data3 = new FData(b);
    return data3;
  }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos pos, CollisionContext c) {
    return getData3(true).custom() ? getShape(s, g, pos, c) : Shapes.block();
  }
}
