package com.example.toy;
import java.util.Arrays;
import net.fabricmc.fabric.api.client.rendering.v1.ArmorRenderer;
import net.minecraft.world.item.Item;
// Mythic Metals' MythicMetalsClient.registerArmorRenderer shape: items picked by instanceof.
public class ToyRenderers {
    static void register(Item[] all) {
        Item[] picked = Arrays.stream(all).filter(i -> i instanceof ToyModelHelmet).toArray(Item[]::new);
        ArmorRenderer.register(() -> {}, picked);
    }
}
