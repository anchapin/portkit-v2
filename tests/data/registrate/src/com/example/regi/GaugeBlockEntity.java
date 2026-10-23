package com.example.regi;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityType; import net.minecraft.world.level.block.state.BlockState;
// The abstract base the block's signature names; no type makes it.
public abstract class GaugeBlockEntity extends BlockEntity {
  protected GaugeBlockEntity(BlockEntityType<?> t, BlockPos p, BlockState s) { super(t, p, s); } }
