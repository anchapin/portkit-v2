package blusunrize.immersiveengineering.common.blocks;

import blusunrize.immersiveengineering.common.register.IEBlockEntities;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import net.minecraft.world.level.block.state.properties.Property;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

/** The fixture's block entities (IE's EnergyConnectorBlockEntity L136-152, RedstoneSwitchboardBlockEntity
 * L163-173, TurntableBlockEntity's mirror while sneaking, one told the point clicked that sets nothing,
 * StripCurtainBlockEntity L172-194/L238-242 (ceiling_attached from the clicked face), TurretBlockEntity's
 * IHasDummyBlocks L470-474, and one setting a state from the point clicked); the curtain also gives its
 * shape (getBlockBounds, L172-177) and copies the item's colour on placement (onBEPlaced, L212-217). */
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

    public static final BooleanProperty CEILING_ATTACHED = BooleanProperty.create("ceiling_attached");

    // StripCurtainBlockEntity's bounds (<clinit>, AABB here as Shapes.box): the 4 wall rails by
    // (facing.ordinal() - 2) % 4, then the ceiling rail along z and along x (getBlockBounds).
    static final VoxelShape[] CURTAIN_SHAPES = {
            Shapes.box(0, 0, 0, 1, 0.1875, 0.0625), Shapes.box(0, 0, 0.9375, 1, 0.1875, 1),
            Shapes.box(0, 0, 0, 0.0625, 0.1875, 1), Shapes.box(0.9375, 0, 0, 1, 0.1875, 1),
            Shapes.box(0, 0.8125, 0.46875, 1, 1, 0.53125), Shapes.box(0.46875, 0.8125, 0, 0.53125, 1, 1)};

    public static class CurtainBE extends Base implements IEBlockInterfaces.IAdvancedDirectionalBE,
            IEBlockInterfaces.IBlockBounds, IEBlockInterfaces.IPlacementInteraction {
        public int colour = -1;
        public CurtainBE(BlockPos p, BlockState s) { super(IEBlockEntities.CURTAIN.get(), p, s); }
        public VoxelShape getBlockBounds(CollisionContext ctx) {
            BlockState state = getBlockState();
            Direction f = state.getValue(FACING_HORIZONTAL);
            if (state.getValue(CEILING_ATTACHED))
                return CURTAIN_SHAPES[f.getAxis() == Direction.Axis.Z ? 4 : 5];
            return CURTAIN_SHAPES[(f.ordinal() - 2) % 4];
        }
        // StripCurtainBlockEntity#onBEPlaced copies the item's colour (a field the shape doesn't read).
        public void onBEPlaced(net.minecraft.world.item.context.BlockPlaceContext ctx) {
            colour = ctx.getClickedFace().ordinal();
        }
        public Property<Direction> getFacingProperty() { return FACING_HORIZONTAL; }
        public PlacementLimitation getFacingLimitation() { return PlacementLimitation.HORIZONTAL; }
        public void onDirectionalPlacement(Direction side, float x, float y, float z, LivingEntity placer) {
            setCeilingAttached(side == Direction.DOWN);
        }
        public void setCeilingAttached(boolean ceilingAttached) {
            BlockState newState = getBlockState().setValue(CEILING_ATTACHED, ceilingAttached);
            level.setBlockAndUpdate(worldPosition, newState);
        }
    }

    /** A curtain whose onDirectionalPlacement also writes a field of its own (not registered). */
    public static class TallyBE extends CurtainBE {
        public int tally;
        public TallyBE(BlockPos p, BlockState s) { super(p, s); }
        @Override
        public void onDirectionalPlacement(Direction side, float x, float y, float z, LivingEntity placer) {
            tally = 1;
            super.onDirectionalPlacement(side, x, y, z, placer);
        }
    }

    public static class MidBE extends Base implements IEBlockInterfaces.IAdvancedDirectionalBE {
        public MidBE(BlockPos p, BlockState s) { super(IEBlockEntities.MID.get(), p, s); }
        public Property<Direction> getFacingProperty() { return FACING_HORIZONTAL; }
        public PlacementLimitation getFacingLimitation() { return PlacementLimitation.HORIZONTAL; }
        public void onDirectionalPlacement(Direction side, float x, float y, float z, LivingEntity placer) {
            level.setBlockAndUpdate(worldPosition, getBlockState().setValue(CEILING_ATTACHED, y > 0.5f));
        }
    }

    public static class TwoHighBE extends Base implements IEBlockInterfaces.IHasDummyBlocks {
        public TwoHighBE(BlockPos p, BlockState s) { super(IEBlockEntities.TWO_HIGH.get(), p, s); }
        public Property<Direction> getFacingProperty() { return FACING_HORIZONTAL; }
        public PlacementLimitation getFacingLimitation() { return PlacementLimitation.HORIZONTAL; }
        public void placeDummies(net.minecraft.world.item.context.BlockPlaceContext ctx, BlockState state) { }
    }
}
