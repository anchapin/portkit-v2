package com.example.elib;
// Zeta's shape: each hub (a Zeta) builds its own variant registry in its constructor.
public class Hub {
  public final Variants variants;
  public Hub(String suffix) { this.variants = new Variants(suffix); }
}
