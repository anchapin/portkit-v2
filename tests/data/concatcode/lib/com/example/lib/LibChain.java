package com.example.lib;
// A library's "creative tab chain" (Zeta's CreativeTabManager shape): start
// ends a chain left open, end walks what was added and clears it.
public class LibChain {
  static Object chain = null;
  static final java.util.List<Object> ADDED = new java.util.ArrayList<>();
  public static void start() { if (chain != null) end(); chain = new Object(); }
  public static void end() { for (Object o : ADDED) { o.hashCode(); } chain = null; }
}
