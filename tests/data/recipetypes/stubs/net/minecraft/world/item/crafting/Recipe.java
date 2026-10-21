package net.minecraft.world.item.crafting;
public interface Recipe {
    boolean matches(Object grid);
    Object assemble(Object grid);
}
