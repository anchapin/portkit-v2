package com.example.cmod;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;
// Immersive Engineering's IEEntityBlock#getCollisionShape, cut down: an
// override that hands the call back to vanilla (super), whose
// BlockBehaviour#getCollisionShape is hasCollision ? the block's getShape :
// Shapes.empty(). ``open`` gives the vanilla answer only when ``c`` isn't
// null, so its answer isn't one shape on every path.
public class CSuper extends Block {
  protected static final VoxelShape SHAPE = box(4.0D, 0.0D, 4.0D, 12.0D, 10.0D, 12.0D);
  private final boolean own;
  private final boolean open;
  public CSuper(Properties p, boolean own, boolean open) { super(p); this.own = own; this.open = open; }
  @Override
  protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
    return own ? SHAPE : super.getShape(s, g, p, c);
  }
  @Override
  protected VoxelShape getCollisionShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
    if (open && g == null) return SHAPE;
    return super.getCollisionShape(s, g, p, c);
  }
}
