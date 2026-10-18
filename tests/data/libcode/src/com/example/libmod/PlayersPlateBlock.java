package com.example.libmod;
import com.example.lib.LibModule; import com.example.lib.LibPlateBlock;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.properties.BlockSetType;
// The mod's own plate: overrides what presses it (Quark's ObsidianPressurePlateBlock shape).
public class PlayersPlateBlock extends LibPlateBlock {
  public PlayersPlateBlock(String name, LibModule module, Properties props) { super(name, module, BlockSetType.STONE, props); }
  @Override protected int getSignalStrength(Level l, BlockPos p) { return 15; }
}
