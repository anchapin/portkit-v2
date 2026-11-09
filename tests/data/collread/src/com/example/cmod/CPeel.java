package com.example.cmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;
// Alex's Mobs BlockBananaPeel's shapes: a 4 px peel to select, a 9 px slab
// (inside the block) to collide with, for every entity alike.
public class CPeel extends Block {
  protected static final VoxelShape SHAPE = box(2.0D, 0.0D, 2.0D, 14.0D, 4.0D, 14.0D);
  protected static final VoxelShape COLLISION = box(0.0D, 0.0D, 0.0D, 16.0D, 9.0D, 16.0D);
  public CPeel(Properties p) { super(p); }
  @Override
  protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return SHAPE; }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return COLLISION; }
}
