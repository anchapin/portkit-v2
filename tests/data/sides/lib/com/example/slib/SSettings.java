package com.example.slib;
// A library's settings object whose field is written on one way of a branch on
// something the run can't know (a system property the JVM defines).
public class SSettings {
  public int glow = 1;
  public int size = 4;
  public SSettings tune() {
    if (System.getProperty("os.name") != null) glow = 9;
    return this;
  }
}
