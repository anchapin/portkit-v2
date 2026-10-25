package appeng.api.orientation;

import java.util.Collection;
import java.util.List;
import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.IntegerProperty;
import net.minecraft.world.level.block.state.properties.Property;

/** AE2's FacingWithSpinStrategy (neoforge/v19.2.18 L60-75): placement by the player's facing and pitch. */
public class FacingWithSpinStrategy implements IOrientationStrategy {
    public static final IntegerProperty SPIN = IntegerProperty.create("spin", 0, 3);
    private final List<Property<?>> properties;

    protected FacingWithSpinStrategy() {
        this.properties = List.of(BlockStateProperties.FACING, SPIN);
    }

    public Direction getFacing(BlockState state) { return state.getValue(BlockStateProperties.FACING); }

    public BlockState setFacing(BlockState state, Direction facing) {
        return state.setValue(BlockStateProperties.FACING, facing);
    }

    public BlockState setSpin(BlockState state, int spin) { return state.setValue(SPIN, spin); }

    @Override
    public BlockState getStateForPlacement(BlockState state, BlockPlaceContext context) {
        var up = Direction.UP;
        var forward = context.getHorizontalDirection().getOpposite();
        var player = context.getPlayer();
        if (player != null) {
            if (player.getXRot() > 65) {
                up = forward.getOpposite();
                forward = Direction.UP;
            } else if (player.getXRot() < -65) {
                up = forward.getOpposite();
                forward = Direction.DOWN;
            }
        }
        return setOrientation(state, forward, up);
    }

    public Collection<Property<?>> getProperties() { return properties; }
}
