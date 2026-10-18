package com.example.imod;
import com.example.ilib.IBlock;
import com.example.ilib.IModule;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
// A mod module: blocks registered by name, then slabs and walls whose names derive from them.
public class JadeModule extends IModule {
  public static Block jade;
  public void register(boolean enabled) {
    Block bricks = new IBlock("jade_bricks", this, Block.Properties.of()).setTab(1);
    lib().variants.addSlabAndWall((IBlock) bricks);
    if (enabled) {
      jade = new IBlock("polished_jade", this, Block.Properties.of());
    }
    lib().variants.addSlabAndWall(new IBlock("jade_tiles", this, Block.Properties.of()));
    lib().variants.addVanillaSlab(Blocks.STONE, this);
    // One object handed two names: what it is called can't be told.
    IBlock twice = new IBlock("onyx", this, Block.Properties.of());
    lib().registry.registerBlock(twice, "onyx_alt");
    lib().variants.addSlabAndWall(twice);
  }
}
