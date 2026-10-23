package com.example.clinit;
import com.example.clinitext.Ext;
import java.util.List;
// Bookkeeping whose every turn may or may not add a capability: what the
// builder's list holds afterwards isn't known.
public class Compat {
  static final List<Object> COMPATS = List.of("energy", "fluid");
  public static void addCaps(TypeBuilder<?> b) {
    for (Object c : COMPATS) { if (Ext.flag()) b.with(c); } } }
