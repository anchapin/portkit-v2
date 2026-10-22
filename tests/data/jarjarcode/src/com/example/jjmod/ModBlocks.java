package com.example.jjmod;
public final class ModBlocks {
  public static final ModRegistry R = ModRegistry.create();
  public static final Object LAMP = R.block("jj_lamp", JJLampBlock::new).register();
}
