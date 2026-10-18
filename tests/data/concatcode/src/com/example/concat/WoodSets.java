package com.example.concat;
import com.example.lib.LibBlock; import com.example.lib.LibChain; import com.example.lib.LibModule; import com.example.lib.LibPlateBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.properties.BlockSetType;
// A helper building a wood set's blocks from the wood's name
// (makeConcatWithConstants), handed the name by each module (Quark's
// WoodSetHandler.addWoodSet shape).
public class WoodSets {
  public static void add(LibModule module, String wood) {
    LibChain.start();
    new LibBlock(wood + "_planks", module, Block.Properties.of());
    new LibPlateBlock(wood + "_pressure_plate", module, BlockSetType.OAK, Block.Properties.of().noCollission());
    new LibBlock(new StringBuilder("stripped_").append(wood).append("_log").toString(), module, Block.Properties.of());
    LibChain.end();
  }
}
