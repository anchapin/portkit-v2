package com.example.toy;
import net.minecraft.world.item.Tier;
public enum ToyTiers implements Tier {
    BRONZE(3, 321, 5.0F), SILVER(2, 640, 7.5F);
    private final int level;
    private final int uses;
    private final float speed;
    ToyTiers(int level, int uses, float speed) { this.level = level; this.uses = uses; this.speed = speed; }
    @Override public int getUses() { return this.uses; }
}
