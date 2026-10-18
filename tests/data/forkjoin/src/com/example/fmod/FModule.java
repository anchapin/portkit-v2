package com.example.fmod;
import com.example.ilib.IModule;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
// Quark's WoodenPostsModule / LeafCarpetModule shapes.
public class FModule extends IModule {
  public void register() {
    new FPost(this, Blocks.STONE);
    new FMixed(this, Blocks.STONE);
    carpet(Blocks.GLOWSTONE);
  }
  // `new` runs before the lookup forks, the constructor after it (LeafCarpetModule#carpetBlock).
  private FCarpet carpet(Block base) {
    return new FCarpet(lib().registryUtil.inherit(base, "%s_carpet"), base, this);
  }
}
