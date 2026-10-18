package net.minecraft.core;
public interface Registry<T> {
  net.minecraft.resources.ResourceLocation getKey(T value);
}
