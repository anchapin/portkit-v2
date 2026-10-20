package com.example.setmod;
import com.example.setlib.SetTypeBuilder;
import net.minecraft.resources.ResourceLocation; import net.minecraft.sounds.SoundEvents;
import net.minecraft.world.level.block.PressurePlateBlock; import net.minecraft.world.level.block.SoundType;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.neoforged.neoforge.registries.DeferredRegister;
// Plates built with set types made in code: through a library builder copying
// a vanilla set type (BetterEnd's sets through WorldWeaver and Fabric API),
// with the one-argument constructor (Quark's wood sets), or spelled out.
public class SetPlates {
  public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("setmod");
  static final BlockSetType ROCK = SetTypeBuilder.copyOf(BlockSetType.STONE).register(id("rock"));
  static final BlockSetType ALLOY = SetTypeBuilder.copyOf(BlockSetType.IRON).soundGroup(SoundType.METAL).register(id("alloy"));
  static final BlockSetType SHY = SetTypeBuilder.copyOf(BlockSetType.OAK)
      .pressurePlateActivationRule(BlockSetType.PressurePlateSensitivity.MOBS).register(id("shy"));
  static final BlockSetType ODD = SetTypeBuilder.copyOf(BlockSetType.STONE)
      .pressurePlateClickOnSound(SoundEvents.METAL_PRESSURE_PLATE_CLICK_ON).register(id("odd"));
  static final BlockSetType UNREGISTERED = SetTypeBuilder.copyOf(BlockSetType.IRON).build(id("unregistered"));
  static final BlockSetType NAMED = BlockSetType.register(new BlockSetType("setmod:named"));
  static final BlockSetType BLOSSOM = BlockSetType.register(new BlockSetType("setmod:blossom", true, true, true,
      BlockSetType.PressurePlateSensitivity.MOBS, SoundType.STONE, null, null, null, null,
      SoundEvents.CHERRY_WOOD_PRESSURE_PLATE_CLICK_OFF, SoundEvents.CHERRY_WOOD_PRESSURE_PLATE_CLICK_ON, null, null));
  static final BlockSetType BUTTONS = BlockSetType.register(new BlockSetType("setmod:buttons", true, true, true,
      BlockSetType.PressurePlateSensitivity.MOBS, SoundType.STONE, null, null, null, null,
      SoundEvents.STONE_BUTTON_CLICK_ON, SoundEvents.STONE_BUTTON_CLICK_ON, null, null));
  public static final Object ROCK_PLATE = BLOCKS.register("rock_plate", () -> new PressurePlateBlock(ROCK, Properties.of()));
  public static final Object ALLOY_PLATE = BLOCKS.register("alloy_plate", () -> new PressurePlateBlock(ALLOY, Properties.of()));
  public static final Object SHY_PLATE = BLOCKS.register("shy_plate", () -> new PressurePlateBlock(SHY, Properties.of()));
  public static final Object ODD_PLATE = BLOCKS.register("odd_plate", () -> new PressurePlateBlock(ODD, Properties.of()));
  public static final Object UNREGISTERED_PLATE = BLOCKS.register("unregistered_plate",
      () -> new PressurePlateBlock(UNREGISTERED, Properties.of()));
  public static final Object NAMED_PLATE = BLOCKS.register("named_plate", () -> new PressurePlateBlock(NAMED, Properties.of()));
  public static final Object BLOSSOM_PLATE = BLOCKS.register("blossom_plate", () -> new PressurePlateBlock(BLOSSOM, Properties.of()));
  public static final Object BUTTONS_PLATE = BLOCKS.register("buttons_plate", () -> new PressurePlateBlock(BUTTONS, Properties.of()));
  static ResourceLocation id(String path) { return ResourceLocation.fromNamespaceAndPath("setmod", path); }
}
