package net.minecraft.world.level.block.state;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level; import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.BlockHitResult; import net.minecraft.world.InteractionResult;
import net.minecraft.world.ItemInteractionResult; import net.minecraft.world.item.ItemStack;
import net.minecraft.world.InteractionHand; import net.minecraft.world.level.block.Block;
import net.minecraft.world.phys.shapes.*;
public abstract class BlockBehaviour { public BlockBehaviour(Properties p) {}
  public static class Properties { public static Properties of() { return null; }
    public static Properties ofFullCopy(BlockBehaviour b) { return null; }
    public Properties noCollission() { return this; } public Properties noOcclusion() { return this; }
    public Properties lightLevel(java.util.function.ToIntFunction<BlockState> f) { return this; }
    public Properties m_60953_(java.util.function.ToIntFunction<BlockState> f) { return this; } }
  protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return null; }
  protected InteractionResult useWithoutItem(BlockState s, Level l, BlockPos p, Player pl, BlockHitResult h) { return null; }
  protected ItemInteractionResult useItemOn(ItemStack i, BlockState s, Level l, BlockPos p, Player pl, InteractionHand h, BlockHitResult r) { return null; }
  protected void neighborChanged(BlockState s, Level l, BlockPos p, Block b, BlockPos f, boolean m) {} }
