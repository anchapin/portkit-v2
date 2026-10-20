package com.example.vlib;
import com.example.ilib.ISlabBlock;
import com.example.ilib.IWallBlock;
import com.example.ilib.IVariantBlock;
import java.util.LinkedHashMap;
import java.util.Map;
import net.minecraft.world.level.block.Block;
// Zeta's VariantRegistry shape: one map per object, built empty in the
// constructor and filled by addSlab (each library instance builds its own).
public class VRegistry {
  public final Map<IVariantBlock, Block> slabs = new LinkedHashMap<>();
  public final Map<IVariantBlock, Block> walls = new LinkedHashMap<>();
  public IVariantBlock addSlab(IVariantBlock block) {
    slabs.put(block, new ISlabBlock(block));
    return block;
  }
  public IVariantBlock addWall(IVariantBlock block) {
    walls.put(block, new IWallBlock(block));
    return block;
  }
}
