package appeng.block;

import appeng.api.orientation.IOrientationStrategy;
import appeng.api.orientation.OrientationStrategies;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.Property;

/** AE2's AEBaseBlock (neoforge/v19.2.18 L49-111), cut down. */
public abstract class AEBaseBlock extends Block {
    protected AEBaseBlock(Properties p) { super(p); }

    public IOrientationStrategy getOrientationStrategy() { return OrientationStrategies.none(); }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder builder) {
        super.createBlockStateDefinition(builder);
        for (Property<?> property : getOrientationStrategy().getProperties()) {
            builder.add(property);
        }
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        var state = this.defaultBlockState();
        return getOrientationStrategy().getStateForPlacement(state, context);
    }
}
