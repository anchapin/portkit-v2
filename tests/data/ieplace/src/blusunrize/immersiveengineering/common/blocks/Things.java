package blusunrize.immersiveengineering.common.blocks;

import blusunrize.immersiveengineering.common.register.IEBlockEntities;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import net.minecraft.world.level.block.state.properties.Property;

/** The fixture's block entities (IE's EnergyConnectorBlockEntity L136-152, RedstoneSwitchboardBlockEntity
 * L163-173, TurntableBlockEntity's mirror while sneaking, and one told the point clicked). */
public class Things {
    public static final DirectionProperty FACING_ALL = DirectionProperty.create("facing", Direction.values());
    public static final DirectionProperty FACING_HORIZONTAL = DirectionProperty.create("facing",
            Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST);

    public abstract static class Base extends BlockEntity implements IEBlockInterfaces.IStateBasedDirectional {
        public Base(net.minecraft.world.level.block.entity.BlockEntityType<?> t, BlockPos p, BlockState s) { super(t, p, s); }
        public BlockState getState() { return null; }
        public void setState(BlockState s) { }
    }

    public static class ConnectorBE extends Base {
        public ConnectorBE(BlockPos p, BlockState s) { super(IEBlockEntities.CONNECTOR.get(), p, s); }
        public Property<Direction> getFacingProperty() { return FACING_ALL; }
        public PlacementLimitation getFacingLimitation() { return PlacementLimitation.SIDE_CLICKED; }
        public boolean mirrorFacingOnPlacement(LivingEntity placer) { return true; }
    }

    public static class BoardBE extends Base {
        public BoardBE(BlockPos p, BlockState s) { super(IEBlockEntities.BOARD.get(), p, s); }
        public Property<Direction> getFacingProperty() { return FACING_HORIZONTAL; }
        public PlacementLimitation getFacingLimitation() { return PlacementLimitation.HORIZONTAL_PREFER_SIDE; }
    }

    public static class SneakBE extends Base {
        public SneakBE(BlockPos p, BlockState s) { super(IEBlockEntities.SNEAK.get(), p, s); }
        public Property<Direction> getFacingProperty() { return FACING_ALL; }
        public PlacementLimitation getFacingLimitation() { return PlacementLimitation.PISTON_LIKE; }
        public boolean mirrorFacingOnPlacement(LivingEntity placer) { return placer.isShiftKeyDown(); }
    }

    public static class HitBE extends Base implements IEBlockInterfaces.IAdvancedDirectionalBE {
        public HitBE(BlockPos p, BlockState s) { super(IEBlockEntities.HIT.get(), p, s); }
        public Property<Direction> getFacingProperty() { return FACING_ALL; }
        public PlacementLimitation getFacingLimitation() { return PlacementLimitation.SIDE_CLICKED; }
        public void onDirectionalPlacement(Direction side, float x, float y, float z, LivingEntity placer) { }
    }
}
