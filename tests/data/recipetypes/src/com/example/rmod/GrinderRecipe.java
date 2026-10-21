package com.example.rmod;
import net.minecraft.world.item.crafting.Recipe;
import net.minecraft.world.item.crafting.RecipeSerializer;
public class GrinderRecipe implements Recipe {
    public boolean matches(Object grid) { return false; }
    public Object assemble(Object grid) { return null; }
    public static class Serializer implements RecipeSerializer<GrinderRecipe> {}
}
