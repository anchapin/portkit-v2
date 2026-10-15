package com.example.deco;

import java.util.function.Supplier;
import net.minecraft.core.BlockPos;
import net.minecraft.core.NonNullList;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.MenuProvider;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ChestMenu;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.BaseEntityBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityTicker;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.entity.ChestBlockEntity;
import net.minecraft.world.level.block.entity.RandomizableContainerBlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Blocks that keep items in a block entity (#179): built directly or
 *  through a registered BlockEntityType, a menu opened or not. */
public class ContainerBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final DeferredRegister ENTITIES = DeferredRegister.createBlocks("examplemod");

    // Built through the registry: the size comes from the type's factory.
    @SuppressWarnings("unchecked")
    public static final Supplier<BlockEntityType<RowBox>> TWO_ROWS =
            (Supplier<BlockEntityType<RowBox>>) ENTITIES.register("two_rows",
                    () -> BlockEntityType.Builder.of((p, s) -> new RowBox(ContainerBlocks.TWO_ROWS.get(), p, s, 2)).build(null));

    public static final Object CRATE = BLOCKS.register("crate", () -> new Crate(Props.of()));
    public static final Object BOX = BLOCKS.register("box", () -> new Box(Props.of()));
    public static final Object TOASTER = BLOCKS.register("toaster", () -> new Toaster(Props.of()));
    public static final Object OVEN = BLOCKS.register("oven", () -> new Oven(Props.of()));
    public static final Object SMOKER = BLOCKS.register("smoker", () -> new Smoker(Props.of()));
    public static final Object VAULT = BLOCKS.register("vault", () -> new Vault(Props.of()));
    public static final Object HAMPER = BLOCKS.register("hamper", () -> new Hamper(Props.of()));
    public static final Object CHEST = BLOCKS.register("chesty", () -> new Chesty(Props.of()));
    public static final Object BIN = BLOCKS.register("bin", () -> new Crate(Props.of()));

    static final class Props { static net.minecraft.world.level.block.state.BlockBehaviour.Properties of() {
        return net.minecraft.world.level.block.state.BlockBehaviour.Properties.of(); } }

    /** Opens its block entity's menu (the usual instanceof + openMenu). */
    public abstract static class Storage extends BaseEntityBlock {
        protected Storage(Properties p) { super(p); }
        @Override
        protected InteractionResult useWithoutItem(BlockState s, Level l, BlockPos p, Player pl, BlockHitResult h) {
            if (!l.isClientSide() && l.getBlockEntity(p) instanceof MenuProvider m) {
                pl.openMenu(m);
            }
            return InteractionResult.SUCCESS;
        }
    }

    public static class Crate extends Storage {
        public Crate(Properties p) { super(p); }
        public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return new CrateEntity(p, s); }
    }

    public static class Box extends Storage {
        public Box(Properties p) { super(p); }
        public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return TWO_ROWS.get().create(p, s); }
    }

    /** Holds two slots, but use puts bread in by hand: no menu. */
    public static class Toaster extends BaseEntityBlock {
        public Toaster(Properties p) { super(p); }
        public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return new Fixed(p, s, 2, false); }
    }

    /** Opens a menu of its own. */
    public static class Oven extends Storage {
        public Oven(Properties p) { super(p); }
        public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return new OvenEntity(p, s); }
    }

    /** A vanilla grid menu, but its block entity ticks. */
    public static class Smoker extends Storage {
        public Smoker(Properties p) { super(p); }
        public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return new Fixed(p, s, 9, false); }
        public <T extends BlockEntity> BlockEntityTicker<T> getTicker(Level l, BlockState s, BlockEntityType<T> t) {
            return () -> {};
        }
    }

    /** More slots than a Bedrock container holds. */
    public static class Vault extends Storage {
        public Vault(Properties p) { super(p); }
        public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return new Fixed(p, s, 60, false); }
    }

    /** A slot count that depends on something unknown. */
    public static class Hamper extends Storage {
        public Hamper(Properties p) { super(p); }
        public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return new Fixed(p, s, External.count(), false); }
    }

    /** Built on vanilla's chest, which has behaviour of its own. */
    public static class Chesty extends Storage {
        public Chesty(Properties p) { super(p); }
        public BlockEntity newBlockEntity(BlockPos p, BlockState s) { return new ChestyEntity(p, s); }
    }

    public static class CrateEntity extends RandomizableContainerBlockEntity {
        private NonNullList<ItemStack> items = NonNullList.withSize(27, ItemStack.EMPTY);
        public CrateEntity(BlockPos p, BlockState s) { super(null, p, s); }
        public int getContainerSize() { return 27; }
        protected AbstractContainerMenu createMenu(int id, Inventory inv) { return ChestMenu.threeRows(id, inv, this); }
    }

    public static class RowBox extends RandomizableContainerBlockEntity {
        private final int size;
        public RowBox(BlockEntityType<?> t, BlockPos p, BlockState s, int rows) { super(t, p, s); this.size = rows * 9; }
        public int getContainerSize() { return size; }
        protected AbstractContainerMenu createMenu(int id, Inventory inv) { return ChestMenu.twoRows(id, inv, this); }
    }

    public static class Fixed extends RandomizableContainerBlockEntity {
        private final int size;
        public Fixed(BlockPos p, BlockState s, int size, boolean x) { super(null, p, s); this.size = size; }
        public int getContainerSize() { return size; }
        protected AbstractContainerMenu createMenu(int id, Inventory inv) { return ChestMenu.threeRows(id, inv, this); }
    }

    public static class OvenEntity extends RandomizableContainerBlockEntity {
        public OvenEntity(BlockPos p, BlockState s) { super(null, p, s); }
        public int getContainerSize() { return 3; }
        protected AbstractContainerMenu createMenu(int id, Inventory inv) { return new OvenMenu(); }
    }

    public static class OvenMenu extends AbstractContainerMenu {}

    public static class ChestyEntity extends ChestBlockEntity {
        public ChestyEntity(BlockPos p, BlockState s) { super(null, p, s); }
    }
}
