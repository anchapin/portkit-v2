package com.example.addon;
import slimeknights.tconstruct.library.materials.stats.*;
/** Not repairable, its id written out. */
public record HandleStats(float speed) implements IMaterialStats {
  public static final MaterialStatsId ID = new MaterialStatsId("tconstruct", "handle");
}
