package com.example.mobs;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.SpawnEggItem;
import net.minecraftforge.common.ForgeSpawnEggItem;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.RegistryObject;

public class ModItems {
    public static final DeferredRegister<Item> REG = DeferredRegister.create(null, "mobs");
    static int GHOST_COLOUR = 0x445566;

    public static final RegistryObject<Item> BEAR_EGG = REG.register("bear_spawn_egg",
            () -> new ForgeSpawnEggItem(ModEntities.BEAR, 0x693A2C, 0x976144, new Item.Properties()));
    // Vanilla's SpawnEggItem takes the type itself; small colours compile to iconst/sipush.
    public static final RegistryObject<Item> MOTH_EGG = REG.register("moth_spawn_egg",
            () -> new SpawnEggItem(ModEntities.MOTH.get(), 5, 200, new Item.Properties()));
    // A colour in a field: the colours are unread, the entity is read.
    public static final RegistryObject<Item> GHOST_EGG = REG.register("ghost_spawn_egg",
            () -> new ForgeSpawnEggItem(ModEntities.GHOST, GHOST_COLOUR, 0xFFFFFF, new Item.Properties()));
    // An entity field no registration stored: the entity is unread, the colours are read.
    public static final RegistryObject<Item> STRAY_EGG = REG.register("stray_spawn_egg",
            () -> new ForgeSpawnEggItem(ModEntities.STRAY, 0x101010, 0x202020, new Item.Properties()));
    public static final RegistryObject<Item> PLAIN = REG.register("plain", () -> new Item(new Item.Properties()));
}
