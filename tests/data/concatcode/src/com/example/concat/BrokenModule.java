package com.example.concat;
import com.example.lib.LibBlock; import com.example.lib.LibChain; import com.example.lib.LibModule;
import net.minecraft.world.level.block.Block;
// Starts a chain and stops part way (a write after a branch the reader can't
// decide), leaving the chain open for whatever runs next.
public class BrokenModule extends LibModule {
  public static int seen;
  public void register(Object event) {
    LibChain.start();
    new LibBlock("maple_" + event, this, Block.Properties.of());
    if (event != null) seen = 1;
    LibChain.end();
  }
}
