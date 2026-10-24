package com.example.nmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// Empty only for a state without lit: every state of this block has it, so it collides.
public class NHas extends NLamp {
  public NHas(Properties p) { super(p); }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
    return s.hasProperty(LIT) ? Shapes.block() : Shapes.empty();
  }
}
