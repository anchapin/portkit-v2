package com.example.setmod;
import com.example.setlib.SetTypeBuilder;
import net.minecraft.resources.ResourceLocation; import net.minecraft.sounds.SoundEvents;
import net.minecraft.world.level.block.DoorBlock; import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.SoundType;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.neoforged.neoforge.registries.DeferredRegister;
// Doors and trapdoors built with set types made in code (#280): copies of a
// vanilla set type through a library builder (BetterEnd's metal and wood sets
// through WorldWeaver and Fabric API), a setter overriding the copied hand,
// the one-argument constructor, the canonical constructor spelled out, and a
// vanilla constant new in 1.21.4 (PALE_OAK).
public class SetDoors {
  public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("setmod");
  static final BlockSetType ROCK = SetTypeBuilder.copyOf(BlockSetType.STONE).register(id("rock"));
  static final BlockSetType ALLOY = SetTypeBuilder.copyOf(BlockSetType.IRON).soundGroup(SoundType.METAL).register(id("alloy"));
  static final BlockSetType WOOD = SetTypeBuilder.copyOf(BlockSetType.OAK).register(id("wood"));
  static final BlockSetType LOCKED = SetTypeBuilder.copyOf(BlockSetType.OAK).openableByHand(false).register(id("locked"));
  static final BlockSetType MIXED = SetTypeBuilder.copyOf(BlockSetType.IRON).doorOpenSound(SoundEvents.WOODEN_DOOR_OPEN)
      .register(id("mixed"));
  static final BlockSetType NAMED = BlockSetType.register(new BlockSetType("setmod:named"));
  static final BlockSetType VERDIGRIS = BlockSetType.register(new BlockSetType("setmod:verdigris", true, false, false,
      BlockSetType.PressurePlateSensitivity.EVERYTHING, SoundType.METAL, SoundEvents.COPPER_DOOR_CLOSE,
      SoundEvents.COPPER_DOOR_OPEN, SoundEvents.COPPER_TRAPDOOR_CLOSE, SoundEvents.COPPER_TRAPDOOR_OPEN,
      null, null, null, null));
  // door sounds where the trapdoor sounds go
  static final BlockSetType SWAPPED = BlockSetType.register(new BlockSetType("setmod:swapped", true, false, false,
      BlockSetType.PressurePlateSensitivity.EVERYTHING, SoundType.METAL, SoundEvents.COPPER_DOOR_CLOSE,
      SoundEvents.COPPER_DOOR_OPEN, SoundEvents.COPPER_DOOR_CLOSE, SoundEvents.COPPER_DOOR_OPEN,
      null, null, null, null));
  public static final Object ROCK_DOOR = BLOCKS.register("rock_door", () -> new DoorBlock(ROCK, Properties.of()));
  public static final Object ALLOY_DOOR = BLOCKS.register("alloy_door", () -> new DoorBlock(ALLOY, Properties.of()));
  public static final Object WOOD_DOOR = BLOCKS.register("wood_door", () -> new DoorBlock(WOOD, Properties.of()));
  public static final Object LOCKED_DOOR = BLOCKS.register("locked_door", () -> new DoorBlock(LOCKED, Properties.of()));
  public static final Object MIXED_DOOR = BLOCKS.register("mixed_door", () -> new DoorBlock(MIXED, Properties.of()));
  public static final Object NAMED_DOOR = BLOCKS.register("named_door", () -> new DoorBlock(NAMED, Properties.of()));
  public static final Object VERDIGRIS_DOOR = BLOCKS.register("verdigris_door", () -> new DoorBlock(VERDIGRIS, Properties.of()));
  public static final Object PALE_DOOR = BLOCKS.register("pale_door", () -> new DoorBlock(BlockSetType.PALE_OAK, Properties.of()));
  public static final Object ALLOY_TRAPDOOR = BLOCKS.register("alloy_trapdoor", () -> new TrapDoorBlock(ALLOY, Properties.of()));
  public static final Object MIXED_TRAPDOOR = BLOCKS.register("mixed_trapdoor", () -> new TrapDoorBlock(MIXED, Properties.of()));
  public static final Object VERDIGRIS_TRAPDOOR = BLOCKS.register("verdigris_trapdoor",
      () -> new TrapDoorBlock(VERDIGRIS, Properties.of()));
  public static final Object SWAPPED_TRAPDOOR = BLOCKS.register("swapped_trapdoor", () -> new TrapDoorBlock(SWAPPED, Properties.of()));
  public static final Object NAMED_TRAPDOOR = BLOCKS.register("named_trapdoor", () -> new TrapDoorBlock(NAMED, Properties.of()));
  static ResourceLocation id(String path) { return ResourceLocation.fromNamespaceAndPath("setmod", path); }
}
