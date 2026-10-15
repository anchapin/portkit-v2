package com.example.books;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
/** Opens the guide through the proxy. */
public class GuideItem extends Item {
  public GuideItem(Item.Properties p) { super(p); }
  public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
    ItemStack stack = player.getItemInHand(hand);
    ExampleMod.PROXY.openGuide(stack);
    return InteractionResultHolder.pass(stack);
  }
}
