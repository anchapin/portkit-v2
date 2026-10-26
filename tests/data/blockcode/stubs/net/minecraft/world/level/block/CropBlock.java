package net.minecraft.world.level.block;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.IntegerProperty;
/** Stand-in: the converter models vanilla CropBlock's constructor itself
 * (blockcode._CROP), so nothing here runs. */
public class CropBlock extends BushBlock {
  public static final IntegerProperty AGE = BlockStateProperties.AGE_7;
  public CropBlock(Properties p) { super(p); }
  protected IntegerProperty getAgeProperty() { return AGE; }
}
