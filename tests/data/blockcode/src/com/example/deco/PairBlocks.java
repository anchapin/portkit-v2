package com.example.deco;

import com.example.registry.Entry;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;

/** Registrations that pass the block and its item as two lambdas in one call. */
public class PairBlocks {
    // Supplier then item Function (MrCrayfish Framework's blockWithItem shape).
    public static final Object PAIR_LAMP = Entry.blockWithItem("pair_lamp",
            () -> new LampBlock(Properties.of().noCollission().lightLevel(s -> 6)),
            b -> new BlockItem(b, new Item.Properties()));
    // A constructor reference for the block, a method reference for the item.
    public static final Object PAIR_STATUE = Entry.blockWithItem("pair_statue", StatueBlock::new, PairBlocks::item);
    // The item Function first.
    public static final Object PAIR_FLIPPED = Entry.itemThenBlock("pair_flipped",
            b -> new BlockItem(b, new Item.Properties()), () -> new Block(Properties.of().lightLevel(s -> 9)));
    // Two Suppliers: one returns a block, the other an item.
    public static final Object PAIR_ITEM_SUPPLIER = Entry.twoSuppliers("pair_item_supplier",
            () -> new Item(new Item.Properties()), () -> new Block(Properties.of().lightLevel(s -> 4)));
    // Two Suppliers that both return a block: which one is registered can't be told.
    public static final Object PAIR_TWO_BLOCKS = Entry.twoSuppliers("pair_two_blocks",
            () -> new Block(Properties.of().lightLevel(s -> 1)), () -> new Block(Properties.of().lightLevel(s -> 2)));
    // A Supplier<?>: javac erases the lambda's return type to Object, so it says nothing.
    public static final Object PAIR_ERASED = Entry.erased("pair_erased",
            () -> new Block(Properties.of()), b -> new BlockItem((Block) b, new Item.Properties()));

    private static BlockItem item(StatueBlock b) {
        return new BlockItem(b, new Item.Properties());
    }
}
