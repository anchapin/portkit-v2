package net.minecraft.world.entity.player;
import java.util.OptionalInt;
import net.minecraft.world.MenuProvider;
public class Player extends net.minecraft.world.entity.LivingEntity { public boolean isShiftKeyDown() { return false; }
  public OptionalInt openMenu(MenuProvider p) { return null; }
  public float getXRot() { return 0f; }
  public boolean isCreative() { return false; } }
