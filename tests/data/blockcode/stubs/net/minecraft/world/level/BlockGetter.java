package net.minecraft.world.level;
public interface BlockGetter {
  default net.minecraft.world.level.block.entity.BlockEntity getBlockEntity(net.minecraft.core.BlockPos p) { return null; } }
