package com.example.fmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;
// A per-object lazy cache (Immersive Engineering IEEntityBlock#getClassData's
// shape): the field starts null, one guarded write fills it from the block's
// own final field, and getCollisionShape reads it.
public class FBlock extends Block {
  private final boolean custom;
  private FData data;
  public FBlock(Properties p, boolean custom) { super(p); this.custom = custom; }
  private FData getData() {
    if (data == null) data = new FData(custom);
    return data;
  }
  @Override
  protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos pos, CollisionContext c) {
    return Shapes.box(0, 0, 0, 1, 0.5, 1);
  }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos pos, CollisionContext c) {
    return getData().custom() ? getShape(s, g, pos, c) : Shapes.box(0, 0, 0, 1, 0.25, 1);
  }
}
