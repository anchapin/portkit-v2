package net.minecraft.world.item;
import net.minecraft.world.level.block.Block;
public class BlockItem extends Item { public BlockItem(Block b, Item.Properties p) { super(p); }
  protected boolean placeBlock(net.minecraft.world.item.context.BlockPlaceContext c, net.minecraft.world.level.block.state.BlockState s) { return true; } }
