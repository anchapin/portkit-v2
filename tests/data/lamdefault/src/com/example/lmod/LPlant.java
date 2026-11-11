package com.example.lmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;
// A block with a shape of its own and no getCollisionShape: it collides
// exactly when the Properties it is built with do.
public class LPlant extends Block {
  protected static final VoxelShape SHAPE = box(2.0D, 0.0D, 2.0D, 14.0D, 13.0D, 14.0D);
  public LPlant(Properties p) { super(p); }
  @Override
  protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return SHAPE; }
}
