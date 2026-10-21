package com.example.render;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.world.level.block.entity.BlockEntity;
// Bound only by the vanilla block entity class: says nothing on its own.
public class AnyRenderer<T extends BlockEntity> implements BlockEntityRenderer<T> { }
