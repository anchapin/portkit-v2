package com.example.nmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.EntityCollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// Supplementaries' SconceBlock shape: a box for projectiles, none for any other entity.
public class NSconce extends NLamp {
  protected static final VoxelShape SHAPE = box(6.0D, 0.0D, 6.0D, 10.0D, 11.0D, 10.0D);
  public NSconce(Properties p) { super(p); }
  @Override
  protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return SHAPE; }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
    return c instanceof EntityCollisionContext ec && ec.getEntity() instanceof Projectile ? s.getShape(g, p) : Shapes.empty();
  }
}
