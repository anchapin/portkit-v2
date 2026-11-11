package com.example.llib;
import com.example.away.Later;
// A supplier whose default method hands it to code that isn't in the jar or
// its libraries (Registrate's NonNullSupplier#lazy and Forge's Lazy.of).
public interface Sup<T> {
  T get();
  default Sup<T> lazy() { return Later.of(this); }
}
