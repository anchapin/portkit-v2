package com.example.regi;
import net.minecraft.world.level.block.entity.BlockEntity; import net.minecraft.world.level.block.entity.BlockEntityType;
// The mod's own block interface (Create's IBE): the block names its type.
public interface TypedBlock<T extends BlockEntity> { BlockEntityType<? extends T> getBlockEntityType(); }
