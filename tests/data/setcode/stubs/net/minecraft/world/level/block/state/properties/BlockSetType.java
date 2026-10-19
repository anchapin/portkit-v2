package net.minecraft.world.level.block.state.properties;
import net.minecraft.sounds.SoundEvent; import net.minecraft.world.level.block.SoundType;
// Signatures only: the record's components, its two constructors and register (client.txt 1.21.8).
public record BlockSetType(String name, boolean canOpenByHand, boolean canOpenByWindCharge,
    boolean canButtonBeActivatedByArrows, PressurePlateSensitivity pressurePlateSensitivity, SoundType soundType,
    SoundEvent doorClose, SoundEvent doorOpen, SoundEvent trapdoorClose, SoundEvent trapdoorOpen,
    SoundEvent pressurePlateClickOff, SoundEvent pressurePlateClickOn, SoundEvent buttonClickOff, SoundEvent buttonClickOn) {
  public static final BlockSetType IRON = null, STONE = null, OAK = null;
  public BlockSetType(String name) { this(name, true, true, true, null, null, null, null, null, null, null, null, null, null); }
  public static BlockSetType register(BlockSetType t) { return t; }
  public enum PressurePlateSensitivity { EVERYTHING, MOBS }
}
