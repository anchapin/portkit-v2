package net.minecraft.world.level.block;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
public abstract class DirectionalBlock extends Block { public static final DirectionProperty FACING = null;
  protected DirectionalBlock(Properties p) { super(p); } }
