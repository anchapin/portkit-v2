package net.minecraftforge.fml.client.registry;
import net.minecraft.client.renderer.tileentity.TileEntitySpecialRenderer;
import net.minecraft.tileentity.TileEntity;
public class ClientRegistry {
  public static <T extends TileEntity> void bindTileEntitySpecialRenderer(Class<T> c, TileEntitySpecialRenderer<? super T> r) { } }
