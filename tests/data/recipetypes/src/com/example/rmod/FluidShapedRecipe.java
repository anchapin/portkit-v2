package com.example.rmod;
import net.minecraft.world.item.crafting.RecipeSerializer;
import net.minecraft.world.item.crafting.ShapedRecipe;
public class FluidShapedRecipe extends ShapedRecipe {
    @Override public boolean matches(Object grid) { return grid != null; }
    @Override public Object getRemainingItems(Object grid) { return grid; }
    public static class Serializer implements RecipeSerializer<FluidShapedRecipe> {}
}
