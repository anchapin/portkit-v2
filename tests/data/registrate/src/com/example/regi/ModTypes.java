package com.example.regi;
import com.tterrag.registrate.util.entry.BlockEntityEntry;
// Registrate chains, as Create's AllBlockEntityTypes declares them.
public class ModTypes {
  static final ModRegistrate REGISTRATE = ModRegistrate.create();
  public static final BlockEntityEntry<SpeedGaugeBlockEntity> SPEED = REGISTRATE
      .blockEntity("speedometer", SpeedGaugeBlockEntity::new).validBlocks().renderer(() -> GaugeRenderer::new).register();
  public static final BlockEntityEntry<StressGaugeBlockEntity> STRESS = REGISTRATE
      .blockEntity("stressometer", StressGaugeBlockEntity::new).renderer(() -> GaugeRenderer::new).register(); }
