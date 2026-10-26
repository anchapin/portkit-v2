package appeng.api.orientation;

import java.util.Collection;
import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import appeng.block.orientation.SpinMapping;

/** AE2's orientation strategy (appeng/api/orientation/IOrientationStrategy.java, neoforge/v19.2.18), cut down. */
public interface IOrientationStrategy {
    Direction getFacing(BlockState state);
    BlockState setFacing(BlockState state, Direction facing);
    BlockState setSpin(BlockState state, int spin);

    default BlockState setUp(BlockState state, Direction up) {
        var facing = getFacing(state);
        var spin = SpinMapping.getSpinFromUp(facing, up);
        return setSpin(state, spin);
    }

    default BlockState setOrientation(BlockState state, Direction facing, Direction up) {
        return setUp(setFacing(state, facing), up);
    }

    default BlockState getStateForPlacement(BlockState state, BlockPlaceContext context) {
        return state;
    }

    Collection<Property<?>> getProperties();
}
