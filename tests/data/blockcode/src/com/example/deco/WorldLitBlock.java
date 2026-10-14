package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;

/** NeoForge's IBlockExtension#getLightEmission override: light from the world. */
public class WorldLitBlock extends Block {
    public WorldLitBlock(Properties p) { super(p); }

    public int getLightEmission(BlockState s, BlockGetter g, BlockPos p) { return 15; }
}
