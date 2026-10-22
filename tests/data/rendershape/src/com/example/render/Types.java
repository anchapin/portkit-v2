package com.example.render;
import java.util.Set;
import net.minecraft.core.Registry;
import net.minecraft.world.level.block.entity.BlockEntityType;
// Block entity types, built the vanilla way and registered.
public class Types {
  public static final BlockEntityType<PoolBlockEntity> POOL = BlockEntityType.Builder.of(PoolBlockEntity::new).build(null);
  public static final BlockEntityType<BearingBlockEntity> BEARING =
      Registry.register(null, "bearing", BlockEntityType.Builder.of(BearingBlockEntity::new).build(null));
  public static final BlockEntityType<ShaftBlockEntity> SHAFT = BlockEntityType.Builder.of(ShaftBlockEntity::new).build(null);
  public static final BlockEntityType<SpinnerBlockEntity> SPINNER = BlockEntityType.Builder.of(SpinnerBlockEntity::new).build(null);
  // Built with the type's own constructor (factory, valid blocks, data type).
  public static final BlockEntityType<TankBlockEntity> TANK = new BlockEntityType<>(TankBlockEntity::new, Set.of(), null);
  public static final BlockEntityType<LampBlockEntity> LAMP = BlockEntityType.Builder.of(LampBlockEntity::new).build(null);
}
