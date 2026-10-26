package appeng.block.storage;

import appeng.api.orientation.IOrientationStrategy;
import appeng.api.orientation.OrientationStrategies;
import appeng.block.AEBaseBlock;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.state.BlockState;

/** An override this reading doesn't follow: it sets its own state on placement. */
public class LitPort extends AEBaseBlock {
    public LitPort(Properties p) { super(p); }

    @Override
    public IOrientationStrategy getOrientationStrategy() { return OrientationStrategies.full(); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        return super.getStateForPlacement(context).setValue(IOPortBlock.POWERED, true);
    }
}
