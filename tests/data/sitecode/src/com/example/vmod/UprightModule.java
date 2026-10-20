package com.example.vmod;
import com.example.ilib.IModule;
import com.example.vlib.VEvent;
// Quark's VerticalSlabsModule#postRegister shape: a variant of every slab in the registry's map.
public class UprightModule extends IModule {
  public void postRegister(VEvent event) {
    event.getVariants().slabs.values().forEach(b -> new UprightBlock(b, this, "%s_upright"));
    event.getVariants().walls.values().forEach(b -> new UprightBlock(b, this, "%s_upright"));
  }
}
