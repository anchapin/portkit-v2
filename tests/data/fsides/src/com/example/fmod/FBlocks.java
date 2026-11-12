package com.example.fmod;
import com.example.llib.LRegistry;
import net.minecraft.world.level.block.Block;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.fml.DistExecutor;
import net.minecraftforge.fml.loading.FMLEnvironment;
import net.minecraftforge.fml.loading.FMLLoader;
// Forge and NeoForge registrations that ask which side they run on (#296).
public class FBlocks {
  static final LRegistry R = LRegistry.forMod("fmod");
  static int[] box = {4};
  // FMLEnvironment.dist compared with Dist.CLIENT: the glow agrees, the size doesn't.
  public static final Block SPLIT = R.define("fside_split", p -> new FBlock(p, 7, FMLEnvironment.dist == Dist.CLIENT ? 3 : 5));
  // NeoForge's FMLEnvironment.dist.isClient().
  public static final Block NEO = R.define("fside_neo", p -> new FBlock(p, 6,
      net.neoforged.fml.loading.FMLEnvironment.dist.isClient() ? 2 : 4));
  // FMLLoader.getDist().isDedicatedServer().
  public static final Block LOADER = R.define("fside_loader", p -> new FBlock(p, 8, FMLLoader.getDist().isDedicatedServer() ? 1 : 2));
  // DistExecutor: runForDist builds different classes; unsafeCallWhenOn gives a value on the client only.
  public static final Block FORKED = R.define("fside_forked", p -> DistExecutor.runForDist(() -> () -> new FClientBlock(p), () -> () -> new FBlock(p, 1, 1)));
  public static final Block CALLED = R.define("fside_called", p -> new FBlock(p, 9,
      DistExecutor.unsafeCallWhenOn(Dist.CLIENT, () -> () -> "client") == null ? 10 : 11));
  // unsafeRunWhenOn on the server side only, which writes the same value both sides start with.
  public static final Block RAN = R.define("fside_ran", p -> {
    DistExecutor.unsafeRunWhenOn(Dist.DEDICATED_SERVER, () -> () -> box[0] = 4);
    return new FBlock(p, box[0], 2); });
}
