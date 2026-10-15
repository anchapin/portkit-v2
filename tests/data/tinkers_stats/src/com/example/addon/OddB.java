package com.example.addon;
import slimeknights.tconstruct.library.materials.stats.*;
/** Declares the same id as OddA with the other answer: the reader drops it. */
public record OddB(int x) implements IMaterialStats {
  public static final MaterialStatsId ID = new MaterialStatsId("tconstruct:odd");
}
