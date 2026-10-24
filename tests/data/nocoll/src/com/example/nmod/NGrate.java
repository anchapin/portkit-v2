package com.example.nmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.EntityCollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// The other way round: only projectiles pass, every other entity collides.
public class NGrate extends NLamp {
  public NGrate(Properties p) { super(p); }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
    return c instanceof EntityCollisionContext ec && ec.getEntity() instanceof Projectile ? Shapes.empty() : Shapes.block();
  }
}
