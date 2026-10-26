package blusunrize.immersiveengineering.common.blocks;

import net.minecraft.core.Direction;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;

/** IEBlockInterfaces cut down (L113-181). */
public class IEBlockInterfaces {
    public interface IDirectionalBE {
        Direction getFacing();
        void setFacing(Direction facing);
        PlacementLimitation getFacingLimitation();
        default Direction getFacingForPlacement(BlockPlaceContext ctx) {
            Direction f = getFacingLimitation().getDirectionForPlacement(ctx);
            return mirrorFacingOnPlacement(ctx.getPlayer()) ? f.getOpposite() : f;
        }
        default boolean mirrorFacingOnPlacement(LivingEntity placer) { return false; }
    }

    public interface BlockstateProvider {
        BlockState getState();
        void setState(BlockState newState);
    }

    public interface IStateBasedDirectional extends IDirectionalBE, BlockstateProvider {
        Property<Direction> getFacingProperty();
        @Override
        default Direction getFacing() { return getState().getValue(getFacingProperty()); }
        @Override
        default void setFacing(Direction facing) {
            BlockState oldState = getState();
            BlockState newState = oldState.setValue(getFacingProperty(), facing);
            setState(newState);
        }
    }

    public interface IAdvancedDirectionalBE extends IDirectionalBE {
        void onDirectionalPlacement(Direction side, float hitX, float hitY, float hitZ, LivingEntity placer);
    }

    public interface IHasDummyBlocks {
        void placeDummies(BlockPlaceContext ctx, BlockState state);
    }

    public interface IPlacementInteraction {
        void onBEPlaced(BlockPlaceContext ctx);
    }
}
