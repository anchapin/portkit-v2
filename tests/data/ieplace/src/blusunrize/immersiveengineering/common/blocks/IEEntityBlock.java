package blusunrize.immersiveengineering.common.blocks;

import blusunrize.immersiveengineering.common.blocks.IEBlockInterfaces.*;
import java.util.function.BiFunction;
import java.util.function.Supplier;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;

/** IEEntityBlock cut down (L61-81, L188-211): the block entity sets facing after placement. */
public class IEEntityBlock<T extends BlockEntity> extends IEBaseBlock {
    private final BiFunction<BlockPos, BlockState, T> makeEntity;

    public IEEntityBlock(Supplier<BlockEntityType<T>> tileType, Properties blockProps) {
        super(blockProps);
        this.makeEntity = (bp, state) -> tileType.get().create(bp, state);
    }

    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) { return makeEntity.apply(pos, state); }

    @Override
    public void onIEBlockPlacedBy(BlockPlaceContext context, BlockState state) {
        Level world = context.getLevel();
        BlockPos pos = context.getClickedPos();
        BlockEntity tile = world.getBlockEntity(pos);
        Player placer = context.getPlayer();
        Direction side = context.getClickedFace();
        float hitX = (float) context.getClickLocation().x - pos.getX();
        float hitY = (float) context.getClickLocation().y - pos.getY();
        float hitZ = (float) context.getClickLocation().z - pos.getZ();
        if (tile instanceof IDirectionalBE directionalBE) {
            Direction f = directionalBE.getFacingForPlacement(context);
            directionalBE.setFacing(f);
            if (tile instanceof IAdvancedDirectionalBE advDirectional)
                advDirectional.onDirectionalPlacement(side, hitX, hitY, hitZ, placer);
        }
        if (tile instanceof IHasDummyBlocks hasDummyBlocks)
            hasDummyBlocks.placeDummies(context, state);
        if (tile instanceof IPlacementInteraction placementInteractionBE)
            placementInteractionBE.onBEPlaced(context);
    }
}
