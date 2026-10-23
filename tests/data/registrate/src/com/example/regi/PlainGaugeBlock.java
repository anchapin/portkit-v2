package com.example.regi;
import net.minecraft.world.level.block.Block;
// Names only the abstract base in its signature, with no type method: unpaired.
public class PlainGaugeBlock extends Block implements TypedBlock<GaugeBlockEntity> {
  public PlainGaugeBlock(Properties p) { super(p); }
  @Override public net.minecraft.world.level.block.entity.BlockEntityType<? extends GaugeBlockEntity> getBlockEntityType() { return null; } }
