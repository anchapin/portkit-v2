package com.example.slib;
import java.util.HashMap;
import java.util.Map;
// A library's static cache of one function (BCLib's SurvivesOnBlockTrait#TAG_CACHE shape):
// private static final, set only by the class initializer, read only by computeIfAbsent.
public class STags {
  private static final Map<String, Integer> CACHE = new HashMap<>();
  private static final Map<String, Integer> THROWS = new HashMap<>();
  public static int size(String key) { return CACHE.computeIfAbsent(key, STags::six); }
  private static final Map<String, Integer> NEVER = new HashMap<>();
  public static int never(String key) { return NEVER.computeIfAbsent(key, STags::refuse); }
  public static int strict(String key) { return THROWS.computeIfAbsent(key, STags::known); }
  // The value whatever the key is.
  private static Integer six(String key) { return 6; }
  // Throws for every key.
  private static Integer refuse(String key) { throw new IllegalArgumentException(key); }
  // Throws for any key it doesn't list.
  private static Integer known(String key) {
    if (key.equals("small")) return 2;
    throw new IllegalArgumentException(key);
  }
}
