package com.example.concat;
import com.example.lib.LibModule;
import net.minecraft.world.item.DyeColor;
// Builds one stool per dye colour; its own code names none of them.
public class StoolModule extends LibModule {
  public void register(Object event) { for (DyeColor c : DyeColor.values()) new StoolBlock(this, c); }
}
