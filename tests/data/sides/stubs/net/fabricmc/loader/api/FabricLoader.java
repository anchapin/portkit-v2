package net.fabricmc.loader.api;
import net.fabricmc.api.EnvType;
// Fabric Loader's API (stand-in; its code isn't there, as in a mod jar).
public interface FabricLoader {
  static FabricLoader getInstance() { return null; }
  EnvType getEnvironmentType();
}
