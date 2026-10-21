package com.example.render;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
// Drawn by a block-entity renderer only: the model is never baked.
public class SpinnerBlock extends Block implements EntityBlock {
  public SpinnerBlock(Properties p) { super(p); }
  public RenderShape getRenderShape(BlockState s) { return RenderShape.ENTITYBLOCK_ANIMATED; }
  public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return new SpinnerBlockEntity(p, s); }
}
