package com.example.vmod;
import com.example.ilib.IModule;
import com.example.vlib.VEvent;
// Quark's NewStoneTypesModule shape: the block, then its slab through the event's registry.
public class JasperModule extends IModule {
  public static JasperBlock jasper;
  public void register(VEvent event) {
    jasper = new JasperBlock(this);
    event.getVariants().addSlab(jasper);
    event.getVariants().addWall(jasper);
  }
}
