package com.example.concat;
import com.example.lib.LibModule;
// Hands its wood's name to the helper (Quark's AzaleaWoodModule shape).
public class MapleModule extends LibModule {
  public void register(Object event) { WoodSets.add(this, "maple"); }
}
