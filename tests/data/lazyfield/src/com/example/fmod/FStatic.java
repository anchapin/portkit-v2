package com.example.fmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// A static cache filled under the class's lock (double-checked).
public class FStatic extends FBlock {
  private static volatile FData shared;
  public FStatic(Properties p) { super(p, true); }
  private static FData getShared() {
    if (shared == null) {
      synchronized (FStatic.class) {
        if (shared == null) shared = new FData(true);
      }
    }
    return shared;
  }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos pos, CollisionContext c) {
    return getShared().custom() ? getShape(s, g, pos, c) : Shapes.block();
  }
}
