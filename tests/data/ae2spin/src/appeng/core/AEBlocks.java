package appeng.core;

import appeng.block.storage.IOPortBlock;
import appeng.block.storage.LitPort;
import appeng.block.storage.WetPress;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Machines placed by an orientation strategy (#296). */
public class AEBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("ae2");
    public static final Object IO_PORT = BLOCKS.register("io_port", () -> new IOPortBlock(Properties.of()));
    public static final Object WET_PRESS = BLOCKS.register("wet_press", () -> new WetPress(Properties.of()));
    public static final Object LIT_PORT = BLOCKS.register("lit_port", () -> new LitPort(Properties.of()));
}
