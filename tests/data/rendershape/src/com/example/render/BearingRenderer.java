package com.example.render;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
// Generic: accepts any block entity that is kinetic AND a bearing.
public class BearingRenderer<T extends KineticBlockEntity & Bearing> implements BlockEntityRenderer<T> {
  public BearingRenderer() { }
  public BearingRenderer(BlockEntityRendererProvider.Context c) { } }
