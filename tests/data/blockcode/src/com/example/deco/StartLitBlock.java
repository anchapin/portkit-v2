package com.example.deco;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;

/** A block drawing one boolean, registered lit: its constructor reads the
 *  state definition through the field (this.stateDefinition.any()), as
 *  Supplementaries' SconceBlock does, rather than getStateDefinition(). */
public class StartLitBlock extends Block {
    public static final BooleanProperty LIT = BlockStateProperties.LIT;

    public StartLitBlock(Properties p) {
        super(p);
        registerDefaultState(this.stateDefinition.any().setValue(LIT, true));
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(LIT); }
}
