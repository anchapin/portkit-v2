package net.minecraftforge.common;
import java.util.function.Supplier;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.SpawnEggItem;
public class ForgeSpawnEggItem extends SpawnEggItem {
    public ForgeSpawnEggItem(Supplier<? extends EntityType<?>> type, int primary, int secondary, Item.Properties p) {
        super(null, primary, secondary, p);
    }
}
