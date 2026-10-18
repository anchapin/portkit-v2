package com.example.concat;
import com.example.lib.LibBlock; import com.example.lib.LibModule;
import java.util.Locale;
import net.minecraft.world.level.block.Block;
// A loop over a mod enum and one over a static final array.
public class GemModule extends LibModule {
  static final String[] STONES = {"slate", "marble"};
  public void register(Object event) {
    for (Gem g : Gem.values()) new LibBlock(g.name().toLowerCase(Locale.ROOT) + "_lamp", this, Block.Properties.of().lightLevel(s -> 9));
    for (String s : STONES) new LibBlock(String.format("%s_tiles", s), this, Block.Properties.of());
    for (int i = 0; i < 2; i++) new LibBlock("tier_" + i + "_" + (i == 0) + "_crate", this, Block.Properties.of());
    float size = 1.5f;
    new LibBlock("odd_" + size + "_block", this, Block.Properties.of());
    new LibBlock(System.getProperty("x") + "_block", this, Block.Properties.of());
    // Not a block: a name handed to code that isn't there with a non-block object.
    java.util.Objects.requireNonNull(new LibModule(), "onyx_" + Gem.RUBY.name().toLowerCase());
  }
}
