package net.minecraft.world.level.block;
import net.minecraft.world.level.block.state.*; import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.phys.shapes.VoxelShape;
public class Block extends BlockBehaviour { public Block(Properties p) { super(p); }
  protected final StateDefinition stateDefinition = null;
  public static VoxelShape box(double a, double b, double c, double d, double e, double f) { return null; }
  public final BlockState defaultBlockState() { return null; }
  public StateDefinition getStateDefinition() { return null; }
  protected final void registerDefaultState(BlockState s) {}
  public BlockState getStateForPlacement(BlockPlaceContext c) { return null; }
  protected void createBlockStateDefinition(StateDefinition.Builder b) {}
  public void setPlacedBy(net.minecraft.world.level.Level l, net.minecraft.core.BlockPos p, BlockState s, net.minecraft.world.entity.LivingEntity e, net.minecraft.world.item.ItemStack i) {}
  public BlockState playerWillDestroy(net.minecraft.world.level.Level l, net.minecraft.core.BlockPos p, BlockState s, net.minecraft.world.entity.player.Player pl) { return s; }
  public static void dropResources(BlockState s, net.minecraft.world.level.Level l, net.minecraft.core.BlockPos p) {}
  public static int getId(BlockState s) { return 0; } }
