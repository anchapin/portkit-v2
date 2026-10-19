package com.example.eref;
// Code that makes an object of whatever class it is handed.
public class Reflector {
  public static Object make(String name) throws Exception { return Class.forName(name).getDeclaredConstructor().newInstance(); }
}
