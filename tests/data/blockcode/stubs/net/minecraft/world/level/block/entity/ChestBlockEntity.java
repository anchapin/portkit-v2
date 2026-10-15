package net.minecraft.world.level.block.entity;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.block.state.BlockState;
public class ChestBlockEntity extends RandomizableContainerBlockEntity {
  public ChestBlockEntity(BlockEntityType<?> t, BlockPos p, BlockState s) { super(t, p, s); }
  public int getContainerSize() { return 27; }
  protected net.minecraft.world.inventory.AbstractContainerMenu createMenu(int i, net.minecraft.world.entity.player.Inventory v) { return null; } }
