package net.minecraft.client.renderer.item;
public interface ClampedItemPropertyFunction extends ItemPropertyFunction { float unclampedCall(net.minecraft.world.item.ItemStack stack, Object level, Object entity, int seed); default float call(net.minecraft.world.item.ItemStack s, Object l, Object e, int i) { return unclampedCall(s, l, e, i); } }
