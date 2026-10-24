package com.example.cmod;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
// Sets one boolean on defaultBlockState() and leaves lit at Block#<init>'s StateDefinition#any (Supplementaries' FirePitBlock shape).
public class CPit extends Block {
  public static final BooleanProperty LIT = BlockStateProperties.LIT;
  public static final BooleanProperty POWERED = BlockStateProperties.POWERED;
  public CPit(Properties p) {
    super(p);
    this.registerDefaultState(this.defaultBlockState().setValue(POWERED, false));
  }
  @Override
  protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(LIT, POWERED); }
}
