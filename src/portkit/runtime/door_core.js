// portkit runtime: the pure rules of a door (#296). No imports; tested with
// node (tests/js/door_core.test.mjs). The Bedrock binding is door.js.
//
// Ported from vanilla Java DoorBlock, read from Mojang's 1.21.1 client jar
// (net.minecraft.world.level.block.DoorBlock, through Mojang's client.txt):
//   getHinge(BlockPlaceContext)  -> hinge() below, line for line
//   useWithoutItem               -> a hand opens it only when its
//                                   BlockSetType#canOpenByHand; the use
//                                   cycles OPEN and plays doorOpen/doorClose
//   neighborChanged              -> powered = either half has a neighbour
//                                   signal; only a change of powered moves
//                                   the door: OPEN = POWERED = powered, with
//                                   the sound when OPEN changes
//   getStateForPlacement         -> placed open when already powered

export const LEFT = "left";
export const RIGHT = "right";

// Direction#getStepX/getStepZ, getCounterClockWise, getClockWise.
export const STEP = { north: [0, -1], south: [0, 1], west: [-1, 0], east: [1, 0] };
export const COUNTER_CLOCKWISE = { north: "west", west: "south", south: "east", east: "north" };
export const CLOCKWISE = { north: "east", east: "south", south: "west", west: "north" };

/**
 * The hinge a door placed facing `facing` gets (DoorBlock#getHinge).
 * `near` describes the four blocks Java looks at: `left`, `leftAbove`,
 * `right`, `rightAbove` (left = the facing turned counter-clockwise), each
 * `{ full, lowerDoor }`: whether its collision shape is a full block, and
 * whether it is the lower half of a door. `click` is where the player
 * clicked, `{ dx, dz }` from the placed block's north-west corner, or null
 * (taken as the centre).
 */
export function hinge(facing, near, click) {
  const n = (k) => near[k] ?? { full: false, lowerDoor: false };
  const score = (n("left").full ? -1 : 0) + (n("leftAbove").full ? -1 : 0)
    + (n("right").full ? 1 : 0) + (n("rightAbove").full ? 1 : 0);
  const leftDoor = n("left").lowerDoor;
  const rightDoor = n("right").lowerDoor;
  if ((leftDoor && !rightDoor) || score > 0) return RIGHT;
  if ((rightDoor && !leftDoor) || score < 0) return LEFT;
  const [stepX, stepZ] = STEP[facing];
  const dx = click ? click.dx : 0.5;
  const dz = click ? click.dz : 0.5;
  return (stepX >= 0 || !(dz < 0.5)) && (stepX <= 0 || !(dz > 0.5))
    && (stepZ >= 0 || !(dx > 0.5)) && (stepZ <= 0 || !(dx < 0.5)) ? LEFT : RIGHT;
}

/** The position of the other half: part 0 is the lower half. */
export function otherHalf(part, loc) {
  return { x: loc.x, y: part === 0 ? loc.y + 1 : loc.y - 1, z: loc.z };
}

/**
 * What a change of redstone does (DoorBlock#neighborChanged): null when the
 * powered state doesn't change, else the new { open, powered } and whether
 * the door's sound plays (it does when open changes).
 */
export function powerChange(state, powered) {
  if (powered === state.powered) return null;
  return { open: powered, powered, sound: powered !== state.open };
}

/** What a use does (DoorBlock#useWithoutItem): null when a hand can't open it. */
export function use(state, hand) {
  if (!hand) return null;
  return { open: !state.open, powered: state.powered, sound: true };
}

/** The sound for a door that is now `open`. */
export function soundFor(door, open) {
  return open ? door.open_sound : door.close_sound;
}
