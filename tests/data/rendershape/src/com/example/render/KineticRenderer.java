package com.example.render;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
// Bound to the mod's own block entity base class: by its signature it
// accepts every kinetic block entity (#354's over-match); the client binds
// it only to the bearing's type (ClientSetup).
public class KineticRenderer<T extends KineticBlockEntity> implements BlockEntityRenderer<T> {
  public KineticRenderer(BlockEntityRendererProvider.Context c) { } }
