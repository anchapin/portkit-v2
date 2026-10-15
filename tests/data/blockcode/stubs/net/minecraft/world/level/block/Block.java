package net.minecraft.world.level.block;
import net.minecraft.world.level.block.state.*; import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.phys.shapes.VoxelShape;
public class Block extends BlockBehaviour { public Block(Properties p) { super(p); }
  public static VoxelShape box(double a, double b, double c, double d, double e, double f) { return null; }
  public final BlockState defaultBlockState() { return null; }
  public StateDefinition getStateDefinition() { return null; }
  protected final void registerDefaultState(BlockState s) {}
  public BlockState getStateForPlacement(BlockPlaceContext c) { return null; }
  protected void createBlockStateDefinition(StateDefinition.Builder b) {} }
