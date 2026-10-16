package net.minecraft.world.item;
public class Item {
    public Item(Properties properties) {}
    public static class Properties {
        public Properties durability(int n) { return this; }
        public Properties stacksTo(int n) { return this; }
    }
}
