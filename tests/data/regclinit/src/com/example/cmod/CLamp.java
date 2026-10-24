package com.example.cmod;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
// Registers lit=true through the stateDefinition field (Supplementaries' SconceBlock shape).
public class CLamp extends Block {
  public static final BooleanProperty LIT = BlockStateProperties.LIT;
  public CLamp(Properties p) {
    super(p);
    this.registerDefaultState(this.stateDefinition.any().setValue(LIT, false).setValue(LIT, true));
  }
  @Override
  protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(LIT); }
}
