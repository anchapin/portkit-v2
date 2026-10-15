package net.minecraft.world.level.block;
import net.minecraft.core.*; import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.*;
public abstract class FaceAttachedHorizontalDirectionalBlock extends HorizontalDirectionalBlock {
  public static final EnumProperty<AttachFace> FACE = null;
  protected FaceAttachedHorizontalDirectionalBlock(Properties p) { super(p); }
  protected boolean canSurvive(BlockState s, LevelReader l, BlockPos p) { return false; }
  protected static Direction getConnectedDirection(BlockState s) { return null; } }
