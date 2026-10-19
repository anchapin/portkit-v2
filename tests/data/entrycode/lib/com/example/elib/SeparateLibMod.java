package com.example.elib;
import net.neoforged.fml.common.Mod;
// ZetaModForge's shape: a library entry class the loader constructs, which builds a second hub.
@Mod("elib_separate")
public class SeparateLibMod { public static Hub OWN; public SeparateLibMod() { OWN = new Hub("_upright_slab"); } }
