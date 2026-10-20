package com.example.pmod;
import net.minecraft.client.renderer.item.ClampedItemPropertyFunction;
import net.minecraft.client.renderer.item.ItemProperties;
import net.minecraft.resources.ResourceLocation;
public class ExampleClient {
    static final ResourceLocation FILL = ResourceLocation.parse("examplemod:fill");
    public static void init() {
        // A live readout: the needle angle, computed every frame.
        ItemProperties.register(ExampleMod.compass, ResourceLocation.fromNamespaceAndPath("examplemod", "angle"),
            (ClampedItemPropertyFunction) (stack, level, entity, seed) -> 0.25F);
        // Through the mod's helpers.
        ItemProperties.register(ExampleMod.gauge, ExampleMod.id("pressure"), (stack, level, entity, seed) -> 0.5F);
        ItemProperties.register(ExampleMod.gauge, ExampleMod.res("level"), (stack, level, entity, seed) -> 0.5F);
        // A static field built in the class initializer.
        ItemProperties.register(ExampleMod.pouch, FILL, (stack, level, entity, seed) -> 1.0F);
        // Vanilla's name on the mod's own item.
        ItemProperties.register(ExampleMod.watch, ResourceLocation.withDefaultNamespace("time"),
            (stack, level, entity, seed) -> 0.5F);
        // The old two-string constructor.
        ItemProperties.register(ExampleMod.watch, new ResourceLocation("examplemod", "phase"),
            (stack, level, entity, seed) -> 0.5F);
    }
}
