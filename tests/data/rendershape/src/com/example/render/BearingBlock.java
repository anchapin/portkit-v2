package com.example.render;
import net.minecraft.world.level.block.Block;
// Its block entity is named only in its generic signature.
public class BearingBlock extends Block implements HasEntity<BearingBlockEntity> { public BearingBlock(Properties p) { super(p); } }
