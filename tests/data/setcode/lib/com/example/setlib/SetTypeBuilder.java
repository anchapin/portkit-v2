package com.example.setlib;
import net.minecraft.resources.ResourceLocation; import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.level.block.SoundType; import net.minecraft.world.level.block.state.properties.BlockSetType;
// A library's set type builder (Fabric API's BlockSetTypeBuilder shape): copyOf
// copies each component of a vanilla set type, setters change one, register
// builds a new BlockSetType and hands it to BlockSetType.register.
public final class SetTypeBuilder {
  private boolean hand = true, wind = true, arrows = true;
  private BlockSetType.PressurePlateSensitivity rule = BlockSetType.PressurePlateSensitivity.EVERYTHING;
  private SoundType sound; private SoundEvent dc, dopen, tc, topen, pOff, pOn, bOff, bOn;
  public static SetTypeBuilder copyOf(BlockSetType t) {
    SetTypeBuilder b = new SetTypeBuilder();
    b.openableByHand(t.canOpenByHand()); b.wind = t.canOpenByWindCharge(); b.arrows = t.canButtonBeActivatedByArrows();
    b.pressurePlateActivationRule(t.pressurePlateSensitivity()); b.soundGroup(t.soundType());
    b.dc = t.doorClose(); b.dopen = t.doorOpen(); b.tc = t.trapdoorClose(); b.topen = t.trapdoorOpen();
    b.pOff = t.pressurePlateClickOff(); b.pressurePlateClickOnSound(t.pressurePlateClickOn());
    b.bOff = t.buttonClickOff(); b.bOn = t.buttonClickOn();
    return b;
  }
  public SetTypeBuilder openableByHand(boolean v) { hand = v; return this; }
  public SetTypeBuilder pressurePlateActivationRule(BlockSetType.PressurePlateSensitivity v) { rule = v; return this; }
  public SetTypeBuilder soundGroup(SoundType v) { sound = v; return this; }
  public SetTypeBuilder pressurePlateClickOnSound(SoundEvent v) { pOn = v; return this; }
  public SetTypeBuilder doorOpenSound(SoundEvent v) { dopen = v; return this; }
  public BlockSetType build(ResourceLocation id) {
    return new BlockSetType(String.valueOf(id), hand, wind, arrows, rule, sound, dc, dopen, tc, topen, pOff, pOn, bOff, bOn);
  }
  public BlockSetType register(ResourceLocation id) { return BlockSetType.register(build(id)); }
}
