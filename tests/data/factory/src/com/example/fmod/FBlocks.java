package com.example.fmod;
import com.example.flib.Builder;
import net.minecraft.world.level.block.Blocks;
// Blocks built by the library's builder from the factory the mod hands it.
public class FBlocks {
  public static final Object WHEATISH = Builder.block("wheatish", FPlant::new).initialProperties(Blocks.WHEAT).register();
  public static final Object STONY = Builder.block("stony", FPlant::new).initialProperties(Blocks.STONE).register();
  public static final Object STONY_OFF = Builder.block("stony_off", FPlant::new).initialProperties(Blocks.STONE).noCollision().register();
  public static final Object TWICE = Builder.block("twice", FPlant::new).initialProperties(Blocks.WHEAT).registerTwice();
}
