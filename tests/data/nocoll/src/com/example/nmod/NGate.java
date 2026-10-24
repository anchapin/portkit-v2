package com.example.nmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// Empty only while lit: some state collides, so the block keeps a box.
public class NGate extends NLamp {
  public NGate(Properties p) { super(p); }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
    return s.getValue(LIT) ? Shapes.empty() : Shapes.box(0, 0, 0, 1, 0.5, 1);
  }
}
