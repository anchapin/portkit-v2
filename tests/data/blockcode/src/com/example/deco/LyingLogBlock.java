package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.ItemInteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.EnumProperty;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.phys.BlockHitResult;

/** A log lying along x or z (the clicked face's axis). What it holds starts
 * EMPTY (registered), is set from the fluid on placement, and changes only
 * when an item is used on it. */
public class LyingLogBlock extends Block {
    public static final EnumProperty<Direction.Axis> AXIS = BlockStateProperties.HORIZONTAL_AXIS;
    public static final EnumProperty<Fill> FILL = EnumProperty.create("fill", Fill.class);

    public LyingLogBlock(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(AXIS, Direction.Axis.X).setValue(FILL, Fill.EMPTY));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(AXIS, ctx.getClickedFace().getAxis()).setValue(FILL,
                ctx.getLevel().getFluidState(ctx.getClickedPos()).getType() == Fluids.WATER ? Fill.WATERLOGGED : Fill.EMPTY);
    }

    @Override
    protected ItemInteractionResult useItemOn(ItemStack i, BlockState s, Level level, BlockPos pos, Player pl,
                                              InteractionHand h, BlockHitResult r) {
        if (s.getValue(FILL) == Fill.EMPTY) {
            level.setBlock(pos, s.setValue(FILL, Fill.MOSS), 3);
            return ItemInteractionResult.SUCCESS;
        }
        return ItemInteractionResult.SUCCESS;
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(AXIS, FILL); }
}
