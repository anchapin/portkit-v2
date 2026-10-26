package appeng.block.storage;

import appeng.api.orientation.IOrientationStrategy;
import appeng.api.orientation.OrientationStrategies;
import appeng.block.AEBaseBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BooleanProperty;

/** A machine like AE2's IOPortBlock: facing and spin from FacingWithSpinStrategy, its own powered
 * registered false and set from its block entity. */
public class IOPortBlock extends AEBaseBlock {
    public static final BooleanProperty POWERED = BooleanProperty.create("powered");

    public IOPortBlock(Properties p) {
        super(p);
        this.registerDefaultState(this.defaultBlockState().setValue(POWERED, false));
    }

    protected BlockState updateBlockStateFromBlockEntity(BlockState currentState, boolean active) {
        return currentState.setValue(POWERED, active);
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder builder) {
        super.createBlockStateDefinition(builder);
        builder.add(POWERED);
    }

    @Override
    public IOrientationStrategy getOrientationStrategy() { return OrientationStrategies.full(); }
}
