package com.example.rmod;
import java.util.function.Supplier;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.crafting.RecipeSerializer;
import net.neoforged.neoforge.registries.DeferredRegister;
public class ModRecipes {
    public static final DeferredRegister<RecipeSerializer<?>> SERIALIZERS = new DeferredRegister<>();
    public static final Object PLAIN = SERIALIZERS.register("plain_shaped", PlainShapedRecipe.Serializer::new);
    public static final Object FLUID = SERIALIZERS.register("fluid_shaped", FluidShapedRecipe.Serializer::new);
    public static final Object GRINDER = SERIALIZERS.register("grinder", () -> new GrinderRecipe.Serializer());
    static { register(new ResourceLocation("rmod", "pressing"), PressSerializer.INSTANCE); }
    static void register(ResourceLocation id, RecipeSerializer<?> s) {}
}
