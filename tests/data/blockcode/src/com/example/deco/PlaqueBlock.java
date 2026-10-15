package com.example.deco;

import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.FaceAttachedHorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.AttachFace;

/** Its own attach rule: on a wall it faces into the wall; on a floor or
 *  ceiling it faces the player. */
public class PlaqueBlock extends FaceAttachedHorizontalDirectionalBlock {
    public PlaqueBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        Direction d = ctx.getClickedFace();
        if (d.getAxis() == Direction.Axis.Y) {
            return defaultBlockState().setValue(FACE, d == Direction.UP ? AttachFace.FLOOR : AttachFace.CEILING)
                    .setValue(FACING, ctx.getHorizontalDirection().getOpposite());
        }
        return defaultBlockState().setValue(FACE, AttachFace.WALL).setValue(FACING, d.getOpposite());
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACE, FACING); }
}
