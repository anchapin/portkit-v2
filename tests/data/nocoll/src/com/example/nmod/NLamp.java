package com.example.nmod;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
// A plain block with one boolean: its collision is its Properties'.
public class NLamp extends Block {
  public static final BooleanProperty LIT = BlockStateProperties.LIT;
  public NLamp(Properties p) {
    super(p);
    this.registerDefaultState(this.stateDefinition.any().setValue(LIT, false));
  }
  @Override
  protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(LIT); }
}
