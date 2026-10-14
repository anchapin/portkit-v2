package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.ItemInteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;

/** FlipBlock's use, but an item in hand is handled first. */
public class ItemFlipBlock extends FlipBlock {
    public ItemFlipBlock(Properties p) { super(p); }

    @Override
    protected ItemInteractionResult useItemOn(ItemStack i, BlockState s, Level l, BlockPos p, Player pl,
                                              InteractionHand h, BlockHitResult r) {
        return ItemInteractionResult.SUCCESS;
    }
}
