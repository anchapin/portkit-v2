package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.HorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.EnumProperty;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** A table two blocks wide, placed as Storage Drawers' framing table is:
 * the clicked half is RIGHT, setPlacedBy puts LEFT counter-clockwise of the
 * facing, and breaking either half removes the other. */
public class TwinTableBlock extends HorizontalDirectionalBlock {
    public static final EnumProperty<TwinPart> PART = EnumProperty.create("part", TwinPart.class);
    private static final VoxelShape TOP = Block.box(0, 14, 0, 16, 16, 16);
    private final boolean removesOther;

    public TwinTableBlock(Properties p, boolean removesOther) {
        super(p);
        this.removesOther = removesOther;
        registerDefaultState(stateDefinition.any().setValue(FACING, Direction.NORTH).setValue(PART, TwinPart.RIGHT));
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING, PART); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        Direction facing = ctx.getHorizontalDirection();
        BlockPos other = ctx.getClickedPos().relative(facing.getCounterClockWise());
        if (ctx.getLevel().getBlockState(other).canBeReplaced(ctx) && ctx.getLevel().getWorldBorder().isWithinBounds(other))
            return defaultBlockState().setValue(FACING, facing);
        return null;
    }

    @Override
    public void setPlacedBy(Level level, BlockPos pos, BlockState state, LivingEntity e, ItemStack stack) {
        super.setPlacedBy(level, pos, state, e, stack);
        if (!level.isClientSide) {
            BlockPos other = pos.relative(state.getValue(FACING).getCounterClockWise());
            level.setBlock(other, state.setValue(PART, TwinPart.LEFT), 3);
        }
    }

    @Override
    public BlockState playerWillDestroy(Level level, BlockPos pos, BlockState state, Player player) {
        if (removesOther && !level.isClientSide) {
            TwinPart part = state.getValue(PART);
            Direction facing = state.getValue(FACING);
            BlockPos other = pos.relative(part == TwinPart.RIGHT ? facing.getCounterClockWise() : facing.getClockWise());
            BlockState there = level.getBlockState(other);
            if (there.is(this) && there.getValue(PART) != part) {
                level.setBlock(other, Blocks.AIR.defaultBlockState(), 35);
                level.levelEvent(player, 2001, other, Block.getId(there));
            }
            if (!player.isCreative() && part == TwinPart.LEFT)
                dropResources(state.setValue(PART, TwinPart.RIGHT), level, other);
        }
        return super.playerWillDestroy(level, pos, state, player);
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return TOP; }
}
