package com.example.clinit;
import com.example.clinitext.Ext;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
// A class initializer whose loop over a list the run can't know writes a
// static: it isn't only bookkeeping, so the run still stops there.
public class WritingTypes {
  static Object last;
  public static final Object BIN;
  static {
    List<Object> seen = new ArrayList<>(Ext.list());
    Iterator<Object> it = seen.iterator();
    while (it.hasNext()) { last = it.next(); }
    BIN = new TypeBuilder<>(BinEntity::new).build(Ext.name()); } }
