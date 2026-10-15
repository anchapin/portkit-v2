package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.FaceAttachedHorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.AttachFace;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** A light switch: vanilla's attach-face placement (inherited), using it
 *  flips enabled on the server, a box per connected direction. */
public class SwitchBlock extends FaceAttachedHorizontalDirectionalBlock {
    public static final BooleanProperty ENABLED = BlockStateProperties.ENABLED;

    public SwitchBlock(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(FACING, Direction.NORTH)
                .setValue(FACE, AttachFace.WALL).setValue(ENABLED, false));
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        return switch (getConnectedDirection(s)) {
            case UP -> Block.box(5, 0, 4, 11, 2, 12);
            case DOWN -> Block.box(5, 14, 4, 11, 16, 12);
            case NORTH -> Block.box(5, 4, 14, 11, 12, 16);
            case SOUTH -> Block.box(5, 4, 0, 11, 12, 2);
            case WEST -> Block.box(14, 4, 5, 16, 12, 11);
            case EAST -> Block.box(0, 4, 5, 2, 12, 11);
        };
    }

    @Override
    protected InteractionResult useWithoutItem(BlockState s, Level level, BlockPos pos, Player player, BlockHitResult hit) {
        if (!level.isClientSide) {
            level.setBlock(pos, s.cycle(ENABLED), 3);
        }
        return InteractionResult.SUCCESS;
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACE, FACING, ENABLED); }
}
