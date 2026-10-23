package com.tterrag.registrate;
import com.tterrag.registrate.builders.BlockEntityBuilder;
import net.minecraft.world.level.block.entity.BlockEntity;
// Signatures of Registrate MC1.20-1.3.3 (tterrag1098/Registrate).
public abstract class AbstractRegistrate<S extends AbstractRegistrate<S>> {
  public <T extends BlockEntity> BlockEntityBuilder<T, S> blockEntity(String name, BlockEntityBuilder.BlockEntityFactory<T> factory) { return null; } }
