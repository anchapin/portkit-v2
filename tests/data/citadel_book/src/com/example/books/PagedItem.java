package com.example.books;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
/** Opens its book at a page, not the root: not a root opener. */
public class PagedItem extends Item {
  public Object screen;
  public PagedItem(Item.Properties p) { super(p); }
  public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
    ItemStack stack = player.getItemInHand(hand);
    screen = new PagedScreen(stack, "intro.json");
    return InteractionResultHolder.pass(stack);
  }
}
