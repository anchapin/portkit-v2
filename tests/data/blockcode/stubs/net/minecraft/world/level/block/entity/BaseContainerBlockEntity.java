package net.minecraft.world.level.block.entity;
import net.minecraft.core.BlockPos; import net.minecraft.world.Container; import net.minecraft.world.MenuProvider;
import net.minecraft.world.entity.player.Inventory; import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.level.block.state.BlockState;
public abstract class BaseContainerBlockEntity extends BlockEntity implements Container, MenuProvider {
  protected BaseContainerBlockEntity(BlockEntityType<?> t, BlockPos p, BlockState s) { super(t, p, s); }
  protected abstract AbstractContainerMenu createMenu(int id, Inventory inv); }
