package net.neoforged.api.distmarker;
// Stand-in (mergetool-api): isClient() is this == CLIENT.
public enum Dist { CLIENT, DEDICATED_SERVER;
  public boolean isDedicatedServer() { return !isClient(); }
  public boolean isClient() { return this == CLIENT; } }
