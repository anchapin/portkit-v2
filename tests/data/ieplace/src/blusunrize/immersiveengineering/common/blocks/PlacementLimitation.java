package blusunrize.immersiveengineering.common.blocks;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.Direction.Axis;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.phys.Vec3;

/** PlacementLimitation cut down (12.4.2-194): four of its rules. */
public enum PlacementLimitation {
    SIDE_CLICKED((side, placer, hitPos) -> side),
    PISTON_LIKE((side, placer, hitPos) -> Direction.orderedByNearest(placer)[0]),
    HORIZONTAL((side, placer, hitPos) -> Direction.fromYRot(placer.getYRot())),
    HORIZONTAL_PREFER_SIDE((side, placer, hitPos) -> side.getAxis() != Axis.Y ? side.getOpposite() : placer.getDirection());

    private final DirectionGetter dirGetter;

    PlacementLimitation(DirectionGetter dirGetter) { this.dirGetter = dirGetter; }

    public Direction getDirectionForPlacement(Direction side, LivingEntity placer, Vec3 clickLocation) {
        return this.dirGetter.getDirectionForPlacement(side, placer, clickLocation);
    }

    public Direction getDirectionForPlacement(BlockPlaceContext context) {
        Vec3 clickLocation = context.getClickLocation();
        BlockPos pos = context.getClickedPos();
        clickLocation = clickLocation.subtract(pos.getX(), pos.getY(), pos.getZ());
        return getDirectionForPlacement(context.getClickedFace(), context.getPlayer(), clickLocation);
    }

    private interface DirectionGetter {
        Direction getDirectionForPlacement(Direction side, LivingEntity placer, Vec3 clickPos);
    }
}
