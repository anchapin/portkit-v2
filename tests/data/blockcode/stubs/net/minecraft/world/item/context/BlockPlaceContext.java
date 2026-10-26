package net.minecraft.world.item.context;
import net.minecraft.core.*; import net.minecraft.world.level.Level;
public class BlockPlaceContext { public Direction getHorizontalDirection() { return null; }
  public Level getLevel() { return null; } public BlockPos getClickedPos() { return null; }
  public Direction getClickedFace() { return null; }
  public net.minecraft.world.phys.Vec3 getClickLocation() { return null; }
  public Direction getNearestLookingDirection() { return null; }
  public Direction[] getNearestLookingDirections() { return null; }
  public net.minecraft.world.entity.player.Player getPlayer() { return null; } }
