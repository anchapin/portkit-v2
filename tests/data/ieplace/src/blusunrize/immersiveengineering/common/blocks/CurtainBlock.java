package blusunrize.immersiveengineering.common.blocks;

import java.util.function.Supplier;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

/** StripCurtainBlock cut down: its states, and IEEntityBlock#getShape (L118-125), the block entity's IBlockBounds. */
public class CurtainBlock<T extends BlockEntity> extends IEEntityBlock<T> {
    public CurtainBlock(Supplier<BlockEntityType<T>> tileType, Properties blockProps) { super(tileType, blockProps); }

    // StripCurtainBlock#createBlockStateDefinition: facing (IEBaseBlock) and ceiling_attached.
    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder builder) {
        builder.add(Things.FACING_HORIZONTAL, Things.CEILING_ATTACHED);
    }

    @Override
    protected VoxelShape getShape(BlockState state, BlockGetter world, BlockPos pos, CollisionContext ctx) {
        BlockEntity be = world.getBlockEntity(pos);
        if (be instanceof IEBlockInterfaces.IBlockBounds bounds)
            return bounds.getBlockBounds(ctx);
        return Shapes.block();
    }
}
