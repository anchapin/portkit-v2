package com.example.cmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.VineBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;
// An override under VineBlock (which declares getShape but no
// getCollisionShape) that hands the call back to vanilla: super runs
// BlockBehaviour#getCollisionShape, hasCollision ? VineBlock's getShape :
// Shapes.empty().
public class CVineSuper extends VineBlock {
  public CVineSuper(Properties p) { super(p); }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
    return super.getCollisionShape(s, g, p, c);
  }
}
