package com.example.deco;

import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.HorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.level.block.state.properties.IntegerProperty;

/** Light from two states its blockstate doesn't draw (Night Lights style):
 *  lit ? brightness : 0, placed lit at brightness 9. */
public class NightLampBlock extends HorizontalDirectionalBlock {
    public static final BooleanProperty LIT = BooleanProperty.create("lit");
    public static final IntegerProperty BRIGHTNESS = IntegerProperty.create("brightness", 0, 15);

    public NightLampBlock(Properties p) {
        super(p.lightLevel(s -> s.getValue(LIT) ? s.getValue(BRIGHTNESS) : 0));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(FACING, ctx.getHorizontalDirection().getOpposite())
                .setValue(BRIGHTNESS, 9).setValue(LIT, true);
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING, LIT, BRIGHTNESS); }
}
