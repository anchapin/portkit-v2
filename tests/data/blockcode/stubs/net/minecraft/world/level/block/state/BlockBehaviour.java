package net.minecraft.world.level.block.state;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.phys.shapes.*;
public abstract class BlockBehaviour { public BlockBehaviour(Properties p) {}
  public static class Properties { public static Properties of() { return null; }
    public static Properties ofFullCopy(BlockBehaviour b) { return null; }
    public Properties noCollission() { return this; } public Properties noOcclusion() { return this; } }
  protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return null; } }
