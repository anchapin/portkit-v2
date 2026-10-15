package com.example.books;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
/** Builds its screen directly in use. */
public class PocketItem extends Item {
  public Object screen;
  public PocketItem(Item.Properties p) { super(p); }
  public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
    ItemStack stack = player.getItemInHand(hand);
    screen = new PocketScreen(stack);
    return InteractionResultHolder.pass(stack);
  }
}
