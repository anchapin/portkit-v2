package com.example.concat;
import com.example.lib.LibBlock; import com.example.lib.LibModule;
import net.minecraft.world.item.DyeColor;
import net.minecraft.world.level.block.Block;
// A block naming itself after its colour (Quark's StoolBlock shape).
public class StoolBlock extends LibBlock {
  public StoolBlock(LibModule module, DyeColor color) { super(color.getName() + "_stool", module, Block.Properties.of()); }
}
