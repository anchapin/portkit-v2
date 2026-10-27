package org.violetmoon.quark.base.handler;

import java.util.HashMap;
import java.util.Map;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import org.violetmoon.zeta.event.bus.LoadEvent;
import org.violetmoon.zeta.event.load.ZRegister;

/** The shape of Quark 4.1's handler (#296): old ids aliased to vanilla's. */
public class QuarkRemapHandler {
    private static final Map<String, String> REMAP = new HashMap<>();

    static {
        REMAP.put("quark:crafter", "minecraft:crafter");
        REMAP.put("quark:polished_tuff", "minecraft:polished_tuff");
        REMAP.put("quark:egg_parrot_grey", "quark:egg_parrot_gray");
    }

    @LoadEvent
    public static void onRemapBlocks(ZRegister event) {
        for (Map.Entry<String, String> e : REMAP.entrySet()) {
            BuiltInRegistries.BLOCK.addAlias(ResourceLocation.parse(e.getKey()), ResourceLocation.parse(e.getValue()));
            BuiltInRegistries.ITEM.addAlias(ResourceLocation.parse(e.getKey()), ResourceLocation.parse(e.getValue()));
        }
    }
}
