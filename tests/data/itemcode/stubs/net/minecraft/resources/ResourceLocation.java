package net.minecraft.resources;
public class ResourceLocation {
    public ResourceLocation(String namespace, String path) {}
    public static ResourceLocation fromNamespaceAndPath(String namespace, String path) { return new ResourceLocation(namespace, path); }
    public String getNamespace() { return ""; }
    public String getPath() { return ""; }
}
