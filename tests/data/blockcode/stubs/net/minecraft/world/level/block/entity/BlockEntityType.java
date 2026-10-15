package net.minecraft.world.level.block.entity;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
public class BlockEntityType<T extends BlockEntity> {
  public T create(BlockPos p, BlockState s) { return null; }
  public interface BlockEntitySupplier<T extends BlockEntity> { T create(BlockPos p, BlockState s); }
  public static class Builder<T extends BlockEntity> {
    public static <T extends BlockEntity> Builder<T> of(BlockEntitySupplier<? extends T> f, Block... blocks) { return null; }
    public BlockEntityType<T> build(Object type) { return null; } } }
