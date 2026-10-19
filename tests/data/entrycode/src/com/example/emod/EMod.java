package com.example.emod;
import com.example.elib.Hub;
import net.neoforged.fml.common.Mod;
// Quark's shape: the mod's entry class holds its hub in a static final its class initializer builds.
@Mod("emod")
public class EMod { public static final Hub HUB = new Hub("_vertical_slab"); public EMod() {} }
