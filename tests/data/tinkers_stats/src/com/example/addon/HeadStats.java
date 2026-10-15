package com.example.addon;
import slimeknights.tconstruct.library.materials.stats.*;
/** Repairable, its id built from a namespace helper. */
public record HeadStats(int durability) implements IRepairableMaterialStats {
  public static final MaterialStatsId ID = new MaterialStatsId(Addon.getResource("head"));
}
