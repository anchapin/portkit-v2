package net.fabricmc.fabric.api.client.rendering.v1;
import net.minecraft.world.item.Item;
public interface ArmorRenderer {
    void render();
    static void register(ArmorRenderer renderer, Item... items) {}
}
