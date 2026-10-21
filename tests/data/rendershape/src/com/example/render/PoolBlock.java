package com.example.render;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
// The shape depends on a constructor field: only a run on the object decides.
public class PoolBlock extends Block implements EntityBlock {
  private final boolean fancy;
  public PoolBlock(Properties p, boolean fancy) { super(p); this.fancy = fancy; }
  public RenderShape getRenderShape(BlockState s) { return fancy ? RenderShape.ENTITYBLOCK_ANIMATED : RenderShape.MODEL; }
  public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return new PoolBlockEntity(p, s); }
}
