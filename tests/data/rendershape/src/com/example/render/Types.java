package com.example.render;
import net.minecraft.core.Registry;
import net.minecraft.world.level.block.entity.BlockEntityType;
// Block entity types, built the vanilla way and registered.
public class Types {
  public static final BlockEntityType<PoolBlockEntity> POOL = BlockEntityType.Builder.of(PoolBlockEntity::new).build(null);
  public static final BlockEntityType<BearingBlockEntity> BEARING =
      Registry.register(null, "bearing", BlockEntityType.Builder.of(BearingBlockEntity::new).build(null));
  public static final BlockEntityType<ShaftBlockEntity> SHAFT = BlockEntityType.Builder.of(ShaftBlockEntity::new).build(null);
  public static final BlockEntityType<SpinnerBlockEntity> SPINNER = BlockEntityType.Builder.of(SpinnerBlockEntity::new).build(null);
}
