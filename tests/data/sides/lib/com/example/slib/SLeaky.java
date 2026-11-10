package com.example.slib;
import java.util.HashMap;
import java.util.Map;
// The same static cache, but also written by put: not a cache of one function.
public class SLeaky {
  private static final Map<String, Integer> CACHE = new HashMap<>();
  public static int size(String key) { return CACHE.computeIfAbsent(key, SLeaky::six); }
  public static void force(String key, int v) { CACHE.put(key, v); }
  private static Integer six(String key) { return 6; }
}
