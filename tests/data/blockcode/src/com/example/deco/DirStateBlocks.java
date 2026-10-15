package com.example.deco;

import net.minecraft.world.level.block.ButtonBlock;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.neoforged.neoforge.registries.DeferredRegister;

/** 6-way facing / attach-face blocks with booleans (tests/test_six_direction_booleans.py). */
public class DirStateBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object FAN = BLOCKS.register("ceiling_fan", () -> new FanBlock(Properties.of().lightLevel(FanBlock::light)));
    public static final Object SWITCH = BLOCKS.register("switch",
            () -> new SwitchBlock(Properties.of().noCollission().lightLevel(s -> s.getValue(SwitchBlock.ENABLED) ? 7 : 0)));
    public static final Object BUTTON = BLOCKS.register("oak_knob", () -> new ButtonBlock(BlockSetType.OAK, 30, Properties.of()));
    public static final Object TOPLIT = BLOCKS.register("top_lit", () -> new TopLitBlock(Properties.of()));
}
