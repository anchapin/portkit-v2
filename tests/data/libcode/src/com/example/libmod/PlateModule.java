package com.example.libmod;
import com.example.lib.LibBlock; import com.example.lib.LibModule; import com.example.lib.LibPlateBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.properties.BlockSetType;
// A module that builds its blocks in an instance method run on a load event
// (Quark's modules' register(ZRegister)), not in a static initializer.
public class PlateModule extends LibModule {
  public static Block plate, lamp, players;
  public final void register(Object event) {
    plate = new LibPlateBlock("lib_stone_plate", this, BlockSetType.STONE, Block.Properties.of().noCollission());
    lamp = new LibBlock("lib_lamp", this, Block.Properties.of().lightLevel(s -> 12));
    players = new PlayersPlateBlock("lib_players_plate", this, Block.Properties.of().noCollission());
  }
}
