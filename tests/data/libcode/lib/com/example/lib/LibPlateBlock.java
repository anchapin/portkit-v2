package com.example.lib;
import net.minecraft.world.level.block.PressurePlateBlock;
import net.minecraft.world.level.block.state.properties.BlockSetType;
// A library plate that registers itself (Zeta's ZetaPressurePlateBlock shape).
public class LibPlateBlock extends PressurePlateBlock {
  public LibPlateBlock(String name, LibModule module, BlockSetType type, Properties props) {
    super(type, props);
    if (module == null) return;
    module.registry.registerBlock(this, name);
  }
}
