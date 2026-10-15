package com.example.deco;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Blocks with facing and boolean states: each way a boolean's starting
 * value, use toggle and light are read (or not). */
public class StateBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    // lit flipped by state.cycle on use; light lit ? 15 : 0.
    public static final Object TOGGLE_LAMP = BLOCKS.register("toggle_lamp", () -> new ToggleLampBlock(
            Properties.of().lightLevel(s -> s.getValue(BlockStateProperties.LIT) ? 15 : 0)));
    // open flipped by setValue(OPEN, !getValue(OPEN)); no light set.
    public static final Object FLIP_BOX = BLOCKS.register("flip_box", () -> new FlipBlock(Properties.of()));
    // The same use, but useItemOn decides first.
    public static final Object ITEM_FLIP = BLOCKS.register("item_flip", () -> new ItemFlipBlock(Properties.of()));
    // powered from redstone, on toggled only when sneaking; light from both.
    public static final Object POWERED_LAMP = BLOCKS.register("powered_lamp", () -> new PoweredLampBlock(
            Properties.of().noCollission().lightLevel(
                    s -> s.getValue(BlockStateProperties.POWERED) ? 12 : (s.getValue(PoweredLampBlock.ON) ? 3 : 0))));
    // A vanilla fence gate: its states are vanilla code.
    public static final Object GATE = BLOCKS.register("gate_block", () -> new GateBlock(Properties.of()));
}
