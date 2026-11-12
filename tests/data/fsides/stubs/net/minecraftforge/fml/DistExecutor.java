package net.minecraftforge.fml;
import java.util.concurrent.Callable;
import java.util.function.Supplier;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.fml.loading.FMLEnvironment;
// Stand-in with fmlcore 1.20.1-47.3.0's bodies (javap).
public final class DistExecutor {
  public static <T> T unsafeCallWhenOn(Dist dist, Supplier<Callable<T>> toRun) {
    if (dist == FMLEnvironment.dist) { try { return toRun.get().call(); } catch (Exception e) { throw new RuntimeException(e); } }
    return null; }
  public static void unsafeRunWhenOn(Dist dist, Supplier<Runnable> toRun) { if (dist == FMLEnvironment.dist) toRun.get().run(); }
  public static void runWhenOn(Dist dist, Supplier<Runnable> toRun) { unsafeRunWhenOn(dist, toRun); }
  public static <T> T runForDist(Supplier<Supplier<T>> client, Supplier<Supplier<T>> server) {
    return FMLEnvironment.dist == Dist.CLIENT ? client.get().get() : server.get().get(); }
}
