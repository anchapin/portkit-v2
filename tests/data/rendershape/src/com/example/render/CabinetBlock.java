package com.example.render;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.BaseEntityBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
// No override: vanilla BaseEntityBlock decides (INVISIBLE in 1.19.2-1.21.1, MODEL from 1.21.2).
public class CabinetBlock extends BaseEntityBlock {
  public CabinetBlock(Properties p) { super(p); }
  public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return null; }
}
