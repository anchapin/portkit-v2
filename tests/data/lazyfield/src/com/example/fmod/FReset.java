package com.example.fmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// The field is written outside its guard too: not a lazy cache.
public class FReset extends FBlock {
  private FData data2;
  public FReset(Properties p) { super(p, true); }
  public void reset() { data2 = new FData(false); }
  private FData getData2() {
    if (data2 == null) data2 = new FData(true);
    return data2;
  }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos pos, CollisionContext c) {
    return getData2().custom() ? getShape(s, g, pos, c) : Shapes.block();
  }
}
