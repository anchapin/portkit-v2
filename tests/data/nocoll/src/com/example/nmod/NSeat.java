package com.example.nmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.EntityCollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;
// Create 6.0.x SeatBlock's shapes: an 8 px slab to select, 3 px for players
// to collide with and 6 px for every other entity.
public class NSeat extends Block {
  protected static final VoxelShape SEAT = box(0.0D, 0.0D, 0.0D, 16.0D, 8.0D, 16.0D);
  protected static final VoxelShape PLAYERS = box(0.0D, 0.0D, 0.0D, 16.0D, 3.0D, 16.0D);
  protected static final VoxelShape OTHERS = box(0.0D, 0.0D, 0.0D, 16.0D, 6.0D, 16.0D);
  public NSeat(Properties p) { super(p); }
  @Override
  protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return SEAT; }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
    if (c instanceof EntityCollisionContext ec && ec.getEntity() instanceof Player)
      return PLAYERS;
    return OTHERS;
  }
}
