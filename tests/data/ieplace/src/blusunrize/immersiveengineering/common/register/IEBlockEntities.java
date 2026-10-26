package blusunrize.immersiveengineering.common.register;

import blusunrize.immersiveengineering.common.blocks.Things.*;
import java.util.Set;
import java.util.function.Supplier;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.neoforged.neoforge.registries.DeferredRegister;

/** IEBlockEntities cut down (<clinit>: register(name, makeType(Foo::new, block))). */
public class IEBlockEntities {
    public static final DeferredRegister REGISTER = DeferredRegister.createBlocks("immersiveengineering");
    public static final Supplier<BlockEntityType<ConnectorBE>> CONNECTOR = reg("connector", makeType(ConnectorBE::new));
    public static final Supplier<BlockEntityType<BoardBE>> BOARD = reg("board", makeType(BoardBE::new));
    public static final Supplier<BlockEntityType<SneakBE>> SNEAK = reg("sneak", makeType(SneakBE::new));
    public static final Supplier<BlockEntityType<HitBE>> HIT = reg("hit", makeType(HitBE::new));

    @SuppressWarnings("unchecked")
    private static <T extends BlockEntity> Supplier<BlockEntityType<T>> reg(String name, Supplier<BlockEntityType<T>> s) {
        return (Supplier<BlockEntityType<T>>) REGISTER.register(name, s);
    }

    private static <T extends BlockEntity> Supplier<BlockEntityType<T>> makeType(BlockEntityType.BlockEntitySupplier<T> f) {
        return () -> new BlockEntityType<>(f, Set.of(), null);
    }
}
