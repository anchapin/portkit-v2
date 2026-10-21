package com.example.render;
import java.util.function.Supplier;
// Where the client side would register its renderers.
public class Renderers {
  public static Supplier<Object> pool() { return PoolRenderer::new; }
  public static Supplier<Object> bearing() { return BearingRenderer::new; }
}
