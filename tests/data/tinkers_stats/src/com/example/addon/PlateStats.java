package com.example.addon;
import slimeknights.tconstruct.library.materials.stats.*;
/** Repairable through a sub-interface; ids made by its own helper. */
public record PlateStats(int armor) implements ScaledStats {
  public static final MaterialStatsId HELMET = makeType("plating_helmet");
  public static final MaterialStatsId BOOTS = makeType("plating_boots");
  private static MaterialStatsId makeType(String name) { return new MaterialStatsId("tconstruct", name); }
}
