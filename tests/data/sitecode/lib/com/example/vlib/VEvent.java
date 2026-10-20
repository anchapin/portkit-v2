package com.example.vlib;
// Zeta's ZRegister shape: the library hands each module its registry through an event.
public interface VEvent {
  VRegistry getVariants();
}
