package appeng.block.storage;

import appeng.api.orientation.IOrientationStrategy;
import appeng.api.orientation.OrientationStrategies;
import appeng.block.AEBaseBlock;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.SimpleWaterloggedBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.material.Fluids;

/** Like AE2's InscriberBlock (L88-94): waterlogged from the clicked position's fluid, added to super's. */
public class WetPress extends AEBaseBlock implements SimpleWaterloggedBlock {
    public WetPress(Properties p) { super(p); }

    @Override
    public IOrientationStrategy getOrientationStrategy() { return OrientationStrategies.full(); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        var fluidState = context.getLevel().getFluidState(context.getClickedPos());
        return super.getStateForPlacement(context)
                .setValue(BlockStateProperties.WATERLOGGED, fluidState.getType() == Fluids.WATER);
    }
}
