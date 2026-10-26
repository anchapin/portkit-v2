package net.minecraft.core;
public enum Direction { DOWN, UP, NORTH, SOUTH, WEST, EAST;
  public Direction getOpposite() { return this; }
  public Direction getClockWise() { return this; }
  public Axis getAxis() { return null; }
  public AxisDirection getAxisDirection() { return null; }
  public static Direction[] orderedByNearest(net.minecraft.world.entity.Entity e) { return null; }
  public static Direction fromYRot(double r) { return null; }
  public enum Axis { X, Y, Z }
  public enum AxisDirection { POSITIVE, NEGATIVE } }
