package com.example.toy;
import java.util.function.Consumer;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.Item;
public class ToyModelHelmet extends ToyPlateItem {
    public ToyModelHelmet(Item.Properties properties) { super(ArmorItem.Type.HELMET, properties); }
    public void initializeClient(Consumer<Object> consumer) { consumer.accept(new ToyModelExtensions()); }
}
