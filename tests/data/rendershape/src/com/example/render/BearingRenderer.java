package com.example.render;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
// Generic: accepts any block entity that is kinetic AND a bearing.
public class BearingRenderer<T extends KineticBlockEntity & Bearing> implements BlockEntityRenderer<T> { }
