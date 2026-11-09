package net.minecraft.world.level.block.state;
// The shape of vanilla BlockBehaviour.Properties (1.21.1) for hasCollision: the
// field starts true (set in the constructor), noCollission() clears it,
// ofLegacyCopy copies it, ofFullCopy copies through ofLegacyCopy, strength
// leaves it alone, odd sets it from a parameter (unread) and maybe clears it
// on a branch (unread).
public abstract class BlockBehaviour {
  protected final Properties properties;
  protected BlockBehaviour(Properties properties) { this.properties = properties; }
  public static class Properties {
    boolean hasCollision = true;
    boolean canOcclude = true;
    float destroyTime;
    public static Properties of() { return new Properties(); }
    public static Properties ofLegacyCopy(BlockBehaviour block) {
      Properties p = new Properties();
      p.destroyTime = block.properties.destroyTime;
      p.hasCollision = block.properties.hasCollision;
      return p;
    }
    public static Properties ofFullCopy(BlockBehaviour block) { return ofLegacyCopy(block); }
    public Properties noCollission() { this.hasCollision = false; this.canOcclude = false; return this; }
    public Properties strength(float time) { this.destroyTime = time; return this; }
    public Properties odd(boolean value) { this.hasCollision = value; return this; }
    public Properties maybe(boolean value) { if (value) { this.hasCollision = false; } return this; }
  }
}
