package net.minecraft.core;
public interface Registry<T> {
  static <V, T extends V> T register(Registry<V> r, String id, T value) { return value; } }
