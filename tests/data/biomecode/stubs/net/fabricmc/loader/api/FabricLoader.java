package net.fabricmc.loader.api;
public interface FabricLoader {
    static FabricLoader getInstance() { return null; }
    boolean isDevelopmentEnvironment();
}
