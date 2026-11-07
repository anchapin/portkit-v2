package com.example.fmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// The same cache filled under a lock (double-checked).
public class FLocked extends FBlock {
  private volatile FData locked;
  public FLocked(Properties p) { super(p, true); }
  private FData getLocked() {
    if (locked == null) {
      synchronized (this) {
        if (locked == null) locked = new FData(true);
      }
    }
    return locked;
  }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos pos, CollisionContext c) {
    return getLocked().custom() ? getShape(s, g, pos, c) : Shapes.block();
  }
}
