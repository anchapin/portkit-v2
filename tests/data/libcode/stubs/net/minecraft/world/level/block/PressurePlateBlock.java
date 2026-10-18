package net.minecraft.world.level.block;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.properties.BlockSetType;
public class PressurePlateBlock extends Block { public PressurePlateBlock(BlockSetType t, Properties p) { super(p); }
  protected int getSignalStrength(Level l, BlockPos p) { return 0; } }
