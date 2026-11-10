package com.example.smod;
import com.example.llib.LRegistry;
import com.example.slib.SLeaky;
import com.example.slib.SSettings;
import com.example.slib.STags;
import net.fabricmc.api.EnvType;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.world.level.block.Block;
// Registrations that ask which side they run on (BetterEnd's shape, #296 pick a).
public class SBlocks {
  static final LRegistry R = LRegistry.forMod("smod");
  static boolean client() { return FabricLoader.getInstance().getEnvironmentType() == EnvType.CLIENT; }
  // Both sides give the same glow; the size differs.
  public static final Block SPLIT = R.define("side_split", p -> new SBlock(p, 7, client() ? 3 : 5));
  // The two sides build different classes.
  public static final Block FORKED = R.define("side_forked", p -> client() ? new SClientBlock(p) : new SBlock(p, 1, 1));
  // A static cache of one function: a known key, an unknown one, an unknown one the function throws on.
  public static final Block CACHED = R.define("side_cached", p -> new SBlock(p, STags.size("glow"), STags.size(System.getProperty("user.home"))));
  public static final Block STRICT = R.define("side_strict", p -> new SBlock(p, STags.strict("small"), STags.strict(System.getProperty("user.home"))));
  public static final Block THROWS = R.define("side_throws", p -> new SBlock(p, 1, STags.never(System.getProperty("user.home"))));
  public static final Block LEAKY = R.define("side_leaky", p -> new SBlock(p, SLeaky.size(System.getProperty("user.home")), 2));
  // A library field written after a branch the run can't decide.
  static final SSettings TUNE = new SSettings().tune();
  public static final Block TUNED = R.define("side_tuned", p -> new SBlock(p, TUNE.glow, TUNE.size));
}
