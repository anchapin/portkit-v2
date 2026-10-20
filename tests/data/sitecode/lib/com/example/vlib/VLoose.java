package com.example.vlib;
import java.util.Map;
// Fields that are not one fresh LinkedHashMap per object.
public class VLoose {
  public final Map<Object, Object> handed;
  public Map<Object, Object> open = new java.util.LinkedHashMap<>();
  public final Map<Object, Object> hashed = new java.util.HashMap<>();
  public VLoose(Map<Object, Object> handed) { this.handed = handed; }
}
