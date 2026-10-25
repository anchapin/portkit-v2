package com.example.bush;

import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.IntegerProperty;
import net.minecraft.world.phys.BlockHitResult;

/** A berry bush: vanilla ``age`` (0-3) and its own ``layers`` (0-2) of snow,
 * both registered at 0; placement into a bush's spot reads the world for
 * ``layers``; the block's own use grows ``age``. */
public class BerryBush extends Block {
    public static final IntegerProperty AGE = BlockStateProperties.AGE_3;
    public static final IntegerProperty SNOW = IntegerProperty.create("layers", 0, 2);

    public BerryBush(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(AGE, 0).setValue(SNOW, 0));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext c) {
        BlockState here = c.getLevel().getBlockState(c.getClickedPos());
        if (here.getBlock() instanceof BerryBush) {
            return defaultBlockState().setValue(SNOW, 1);
        }
        return defaultBlockState();
    }

    @Override
    protected InteractionResult useWithoutItem(BlockState s, Level level, BlockPos pos, Player pl, BlockHitResult r) {
        level.setBlock(pos, s.setValue(AGE, s.getValue(AGE) + 1), 3);
        return InteractionResult.SUCCESS;
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(AGE, SNOW); }
}
