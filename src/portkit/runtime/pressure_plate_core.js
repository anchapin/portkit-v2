// portkit runtime: the pure rules of a pressure plate (#296). No imports;
// tested with node (tests/js/pressure_plate.test.mjs). The Bedrock
// binding is pressure_plate.js.
//
// Ported from vanilla Java BasePressurePlateBlock and PressurePlateBlock, read
// from Mojang's 1.21.1 client jar (through Mojang's client.txt):
//   TOUCH_AABB          -> the touch box (x/z 1/16..15/16, y 0..4/16), from the table
//   getSignalStrength   -> 15 when an entity of class Entity (EVERYTHING) or
//                          LivingEntity (MOBS) is in the touch box and passes
//                          EntitySelector.NO_SPECTATORS and
//                          !isIgnoringBlockTriggers(); else 0
//   entityInside        -> an unpressed plate checks at once
//   tick / checkPressed -> a pressed plate re-checks getPressedTime() (20)
//                          ticks after each check; it releases at the first
//                          re-check that finds nobody. Pressing plays
//                          pressurePlateClickOn, releasing ...ClickOff.
// What Bedrock can't give: Java checks the tick an entity moves in; here an
// unpressed plate looks every few ticks (minecraft:tick, see plates.py), and
// an entity counts when its position (not its box) is in the touch box.

/** Whether `loc` (an entity's position) is in the touch box of the plate at `at`. */
export function inTouchBox(touch, at, loc) {
  const axes = ["x", "y", "z"];
  return axes.every((a, i) => {
    const v = loc[a] - at[a];
    return v >= touch.min[i] && v <= touch.max[i];
  });
}

/**
 * Whether one entity presses the plate. `entity` is { typeId, mob, spectator }:
 * mob = a Bedrock "mob" family member (players count as mobs: Java's Player is a
 * LivingEntity), spectator = a player in spectator mode.
 */
export function presses(entity, mobsOnly) {
  if (entity.spectator) return false;
  if (!mobsOnly) return true;
  return entity.typeId === "minecraft:player" || entity.mob === true;
}

/**
 * One look at a plate. `powered` its state now, `present` whether something
 * presses it, `now` the current tick, `due` the tick its next re-check is due
 * (undefined when not known, e.g. after a reload: checked now).
 * Returns { powered, sound: "on" | "off" | null, due } (due undefined once released).
 */
export function step(powered, present, now, due, pressedTicks) {
  if (!powered) {
    if (!present) return { powered: false, sound: null, due: undefined };
    return { powered: true, sound: "on", due: now + pressedTicks };
  }
  if (due !== undefined && now < due) return { powered: true, sound: null, due };
  if (present) return { powered: true, sound: null, due: now + pressedTicks };
  return { powered: false, sound: "off", due: undefined };
}
