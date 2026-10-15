package com.example.mobs;
import java.util.function.Supplier;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.RegistryObject;

// Entity registrations in the shapes portkit.entities reads (and two it can't
// fully read). Alex's Mobs builds the type in the lambda through a helper
// (registerEntity); Mantle-style helpers take a Supplier of the Builder.
public class ModEntities {
    public static final DeferredRegister<EntityType<?>> REG = DeferredRegister.create(null, "mobs");
    static float GHOST_SIZE = 0.9F;

    public static final RegistryObject<EntityType<Bear>> BEAR = REG.register("bear",
            () -> EntityType.Builder.of(Bear::new, MobCategory.CREATURE).sized(1.4F, 1.4F).clientTrackingRange(10).build("bear"));
    public static final RegistryObject<EntityType<Bear>> MOTH = REG.register("moth",
            () -> registerEntity(EntityType.Builder.of(Bear::new, MobCategory.AMBIENT).sized(0.5F, 0.25F), "moth"));
    // The hitbox is a field, not a constant: unread.
    public static final RegistryObject<EntityType<Bear>> GHOST = REG.register("ghost",
            () -> EntityType.Builder.of(Bear::new, MobCategory.MONSTER).sized(GHOST_SIZE, 2.0F).build("ghost"));
    public static final RegistryObject<EntityType<?>> SLIME = registerBuilder("slime",
            () -> EntityType.Builder.of(Bear::new, MobCategory.MONSTER).sized(2.0F, 1.0F));
    // Not stored by a registration: an egg naming it can't say which entity.
    public static RegistryObject<EntityType<Bear>> STRAY = null;

    static <T extends Bear> EntityType<T> registerEntity(EntityType.Builder<T> builder, String id) {
        return builder.build(id);
    }

    static RegistryObject<EntityType<?>> registerBuilder(String name, Supplier<EntityType.Builder<?>> builder) {
        return null;
    }
}
