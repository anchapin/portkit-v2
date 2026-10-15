package net.minecraft.world.entity;
public class EntityType<T extends Entity> {
    public interface EntityFactory<T extends Entity> { T create(EntityType<T> type, Object level); }
    public static class Builder<T extends Entity> {
        public static <T extends Entity> Builder<T> of(EntityFactory<T> factory, MobCategory category) { return null; }
        public Builder<T> sized(float width, float height) { return this; }
        public Builder<T> clientTrackingRange(int range) { return this; }
        public EntityType<T> build(String id) { return null; }
    }
}
