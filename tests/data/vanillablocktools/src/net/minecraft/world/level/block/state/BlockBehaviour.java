package net.minecraft.world.level.block.state;
// The shape of vanilla BlockBehaviour.Properties (1.21.1): requiresCorrectToolForDrops()
// sets the flag, ofLegacyCopy copies it, ofFullCopy copies through ofLegacyCopy,
// strength leaves it alone, and odd sets it from a parameter (unread).
public abstract class BlockBehaviour {
  protected final Properties properties;
  protected BlockBehaviour(Properties properties) { this.properties = properties; }
  public static class Properties {
    boolean requiresCorrectToolForDrops;
    float destroyTime;
    public static Properties of() { return new Properties(); }
    public static Properties ofLegacyCopy(BlockBehaviour block) {
      Properties p = new Properties();
      p.destroyTime = block.properties.destroyTime;
      p.requiresCorrectToolForDrops = block.properties.requiresCorrectToolForDrops;
      return p;
    }
    public static Properties ofFullCopy(BlockBehaviour block) { return ofLegacyCopy(block); }
    public Properties requiresCorrectToolForDrops() { this.requiresCorrectToolForDrops = true; return this; }
    public Properties strength(float time) { this.destroyTime = time; return this; }
    public Properties odd(boolean value) { this.requiresCorrectToolForDrops = value; return this; }
  }
}
