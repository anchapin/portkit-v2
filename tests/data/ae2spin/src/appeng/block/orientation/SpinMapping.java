package appeng.block.orientation;

import net.minecraft.core.Direction;

/** AE2's SpinMapping (neoforge/v19.2.18 L14-42). */
public final class SpinMapping {
    private static final Direction[][] SPIN_DIRECTIONS = new Direction[][] {
            { Direction.NORTH, Direction.WEST, Direction.SOUTH, Direction.EAST },
            { Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST },
            { Direction.UP, Direction.WEST, Direction.DOWN, Direction.EAST },
            { Direction.UP, Direction.EAST, Direction.DOWN, Direction.WEST },
            { Direction.UP, Direction.SOUTH, Direction.DOWN, Direction.NORTH },
            { Direction.UP, Direction.NORTH, Direction.DOWN, Direction.SOUTH },
    };

    public static int getSpinFromUp(Direction facing, Direction up) {
        var spinDirs = SPIN_DIRECTIONS[facing.ordinal()];
        for (int i = 0; i < spinDirs.length; i++) {
            if (spinDirs[i] == up) {
                return i;
            }
        }
        return 0;
    }
}
