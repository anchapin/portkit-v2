package com.example.deco;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Every way a block's light is set (or not) that read_light distinguishes. */
public class LightBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    // One Properties object several registrations share.
    static final Properties SHARED = Properties.of();
    // state -> 12: one value for every state.
    public static final Object GLOW = BLOCKS.register("glow", () -> new Block(Properties.of().lightLevel(s -> 12)));
    // Code-only lit/brightness, read at the placed state.
    public static final Object NIGHT_LAMP = BLOCKS.register("night_lamp", () -> new NightLampBlock(Properties.of()));
    // lit ? 15 : 0 on a block whose blockstate draws lit.
    public static final Object TOGGLE = BLOCKS.register("toggle", () -> new Block(Properties.of()
            .lightLevel(s -> s.getValue(BlockStateProperties.LIT) ? 15 : 0)));
    // A vanilla block's Properties: its light is glowstone's.
    public static final Object COPY = BLOCKS.register("copy", () -> new Block(Properties.ofFullCopy(Blocks.GLOWSTONE)));
    // ...unless the copy sets its own afterwards.
    public static final Object COPY_SET = BLOCKS.register("copy_set",
            () -> new Block(Properties.ofFullCopy(Blocks.GLOWSTONE).lightLevel(s -> 3)));
    public static final Object WORLD_LIT = BLOCKS.register("world_lit", () -> new WorldLitBlock(Properties.of()));
    public static final Object TOO_BRIGHT = BLOCKS.register("too_bright",
            () -> new Block(Properties.of().lightLevel(s -> 20)));
    public static final Object PLAIN = BLOCKS.register("plain", () -> new Block(Properties.of()));
    // A renamed (Forge SRG) setting: which one it is can't be told.
    public static final Object RENAMED = BLOCKS.register("renamed",
            () -> new Block(Properties.of().m_60953_(s -> 7)));
    // The builder's return value thrown away: Properties change in place.
    public static final Object DISCARDED = BLOCKS.register("discarded", LightBlocks::discarded);
    // A vanilla block class whose Properties aren't its first argument.
    public static final Object DOOR = BLOCKS.register("door",
            () -> new DoorBlock(BlockSetType.OAK, Properties.of().lightLevel(s -> 5)));

    // Java's builder changes itself: SHARED_LIT lights SHARED for every block
    // built from it afterwards, so SHARED_PLAIN's light depends on which of
    // the two registers first. Neither is read.
    public static final Object SHARED_LIT = BLOCKS.register("shared_lit",
            () -> new Block(SHARED.lightLevel(s -> 15)));
    public static final Object SHARED_PLAIN = BLOCKS.register("shared_plain", () -> new Block(SHARED));

    private static Block discarded() {
        Properties p = Properties.of();
        p.lightLevel(s -> 7);
        return new Block(p);
    }
}
