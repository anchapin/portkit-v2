package com.example.jjmod;
import com.example.jjlib.BuilderRegistry;
// The mod's own subclass of the bundled registry: its block(...) calls are
// compiled against this class but resolve to the library's method.
public final class ModRegistry extends BuilderRegistry<ModRegistry> {
  public static ModRegistry create() { return new ModRegistry(); }
}
