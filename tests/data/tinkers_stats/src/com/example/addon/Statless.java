package com.example.addon;
import slimeknights.tconstruct.library.materials.stats.*;
/** Not repairable: an enum whose constructor builds the id. */
public enum Statless implements IMaterialStats {
  BINDING("binding"), BOWSTRING("bowstring");
  private final MaterialStatsId id;
  Statless(String name) { this.id = new MaterialStatsId(Addon.getResource(name)); }
}
