package com.example.elib;
// Zeta's ForgeZRegister shape: made by a hub whenever the loader's register event fires.
public class HubEvent implements Event {
  private final Hub hub;
  public HubEvent(Hub hub) { this.hub = hub; }
  public Variants variants() { return hub.variants; }
  public static Event fire(Hub hub) { return new HubEvent(hub); }
}
