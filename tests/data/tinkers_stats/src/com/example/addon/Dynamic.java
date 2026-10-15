package com.example.addon;
import slimeknights.tconstruct.library.materials.stats.*;
/** An id from a runtime string: unreadable, left out. */
public record Dynamic(int x) implements IRepairableMaterialStats {
  public static final MaterialStatsId ID = new MaterialStatsId("tconstruct", System.getProperty("x"));
}
