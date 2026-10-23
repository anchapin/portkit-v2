package com.example.regi;
import net.minecraft.world.level.block.Block; import net.minecraft.world.level.block.entity.BlockEntityType;
// One class for two blocks: the field picks the type (Create's GaugeBlock).
public class GaugeBlock extends Block implements TypedBlock<GaugeBlockEntity> {
  final boolean speed;
  public GaugeBlock(Properties p, boolean speed) { super(p); this.speed = speed; }
  @Override public BlockEntityType<? extends GaugeBlockEntity> getBlockEntityType() {
    if (speed) return ModTypes.SPEED.get();
    return ModTypes.STRESS.get(); } }
