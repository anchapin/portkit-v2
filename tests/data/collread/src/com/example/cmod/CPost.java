package com.example.cmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;
// A fence-like post: its collision box of its own reaches above the block,
// which Bedrock's collision box can't, so it stays a DEFAULT.
public class CPost extends Block {
  protected static final VoxelShape SHAPE = box(6.0D, 0.0D, 6.0D, 10.0D, 16.0D, 10.0D);
  protected static final VoxelShape COLLISION = box(6.0D, 0.0D, 6.0D, 10.0D, 24.0D, 10.0D);
  public CPost(Properties p) { super(p); }
  @Override
  protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return SHAPE; }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return COLLISION; }
}
