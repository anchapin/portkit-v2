package com.example.llib;
import java.util.function.Function;
// A library's functional interface with a default method, Registrate's
// NonNullFunction shape (#296): f.andThen(g) is x -> g.apply(f.apply(x)).
public interface Fn<T, R> extends Function<T, R> {
  @Override
  R apply(T t);
  default <V> Fn<T, V> andThen(Fn<? super R, ? extends V> after) {
    return t -> after.apply(apply(t));
  }
  static <T> Fn<T, T> identity() { return t -> t; }
}
