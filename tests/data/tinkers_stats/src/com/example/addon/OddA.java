package com.example.addon;
import slimeknights.tconstruct.library.materials.stats.*;
public record OddA(int x) implements IRepairableMaterialStats {
  public static final MaterialStatsId ID = new MaterialStatsId("tconstruct:odd");
}
