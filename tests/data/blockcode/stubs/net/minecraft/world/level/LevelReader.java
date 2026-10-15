package net.minecraft.world.level;
import net.minecraft.core.BlockPos; import net.minecraft.world.level.block.state.BlockState;
public interface LevelReader extends BlockGetter { BlockState getBlockState(BlockPos p); }
