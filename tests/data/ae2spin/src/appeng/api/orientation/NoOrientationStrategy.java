package appeng.api.orientation;

import java.util.Collection;
import java.util.List;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;

public class NoOrientationStrategy implements IOrientationStrategy {
    public Direction getFacing(BlockState state) { return Direction.NORTH; }
    public BlockState setFacing(BlockState state, Direction facing) { return state; }
    public BlockState setSpin(BlockState state, int spin) { return state; }
    public Collection<Property<?>> getProperties() { return List.of(); }
}
