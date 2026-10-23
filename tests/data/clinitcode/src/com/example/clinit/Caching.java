package com.example.clinit;
import java.lang.ref.WeakReference;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.world.level.block.entity.BlockEntity;
// A provider that caches the renderer it built for the context it was given.
public class Caching<T extends BlockEntity> implements BlockEntityRendererProvider<T> {
  private final BlockEntityRendererProvider<T> inner;
  private WeakReference<Context> cachedContext;
  private WeakReference<BlockEntityRenderer<T>> cachedRenderer;
  Caching(BlockEntityRendererProvider<T> inner) { this.inner = inner; }
  @Override public BlockEntityRenderer<T> create(Context c) {
    BlockEntityRenderer<T> r = cachedRenderer == null ? null : cachedRenderer.get();
    if (cachedContext == null || cachedContext.get() != c || r == null) {
      r = inner.create(c);
      cachedContext = new WeakReference<>(c);
      cachedRenderer = new WeakReference<>(r); }
    return r; } }
