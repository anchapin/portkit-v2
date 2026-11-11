package com.example.lmod;
import com.example.llib.Builder;
import net.minecraft.world.level.block.Blocks;
// Blocks built by the library's builder with two properties(...) calls
// (Create's package_frogport has noOcclusion, then mapColor and sound).
public class LBlocks {
  public static final Object TWO_KEEP = Builder.block("two_keep", LPlant::new).initialProperties(Blocks.STONE)
      .properties(p -> p).properties(p -> p).register();
  public static final Object TWO_OFF = Builder.block("two_off", LPlant::new).initialProperties(Blocks.STONE)
      .properties(p -> p).properties(p -> p.noCollission()).register();
  public static final Object OFF_FIRST = Builder.block("off_first", LPlant::new).initialProperties(Blocks.STONE)
      .properties(p -> p.noCollission()).properties(p -> p).register();
  public static final Object LAZY = Builder.block("lazy_one", LPlant::new).initialProperties(Blocks.WHEAT)
      .properties(p -> p).registerLazy();
}
