package com.example.nmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// noCollission Properties, but an override that collides: the override wins, as in Java.
public class NSolid extends NLamp {
  public NSolid(Properties p) { super(p); }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return Shapes.block(); }
}
