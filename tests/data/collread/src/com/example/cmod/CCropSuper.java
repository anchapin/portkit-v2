package com.example.cmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.CropBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;
// An override under CropBlock that hands the call back to vanilla (super).
public class CCropSuper extends CropBlock {
  public CCropSuper(Properties p) { super(p); }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
    return super.getCollisionShape(s, g, p, c);
  }
}
