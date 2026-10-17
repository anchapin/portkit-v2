package com.example.ores;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.loader.api.FabricLoader;
public class ExampleMod implements ModInitializer {
    public static ModConfig CONFIG;
    public static boolean dev;
    @Override
    public void onInitialize() {
        if (FabricLoader.getInstance().isDevelopmentEnvironment()) {
            dev = true;
        }
        OreFeatures.init();
    }
}
