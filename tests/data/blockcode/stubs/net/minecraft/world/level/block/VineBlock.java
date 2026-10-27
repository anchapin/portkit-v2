package net.minecraft.world.level.block;
import net.minecraft.core.*; import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
public class VineBlock extends Block { public static final BooleanProperty UP = null, NORTH = null, EAST = null, SOUTH = null, WEST = null;
  public VineBlock(Properties p) { super(p); }
  public boolean canSupportAtFace(BlockGetter g, BlockPos p, Direction d) { return false; } }
