package blusunrize.immersiveengineering.common.blocks;

import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;

/** BlockItemIE#placeBlock (L95-108). */
public class BlockItemIE extends BlockItem {
    public BlockItemIE(Block b) { super(b, new Item.Properties()); }

    @Override
    protected boolean placeBlock(BlockPlaceContext context, BlockState newState) {
        Block b = newState.getBlock();
        if (b instanceof IEBaseBlock ieBlock) {
            if (!ieBlock.canIEBlockBePlaced(newState, context))
                return false;
            boolean ret = super.placeBlock(context, newState);
            if (ret)
                ieBlock.onIEBlockPlacedBy(context, newState);
            return ret;
        } else
            return super.placeBlock(context, newState);
    }
}
