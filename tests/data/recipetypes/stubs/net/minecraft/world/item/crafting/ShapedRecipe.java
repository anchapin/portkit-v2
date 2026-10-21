package net.minecraft.world.item.crafting;
public class ShapedRecipe implements Recipe {
    public boolean matches(Object grid) { return true; }
    public Object assemble(Object grid) { return null; }
    public Object getRemainingItems(Object grid) { return null; }
}
