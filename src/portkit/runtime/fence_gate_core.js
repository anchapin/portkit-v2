// portkit runtime: the pure rules of a fence gate (#367). No imports; tested with node
// (tests/js/fence_gate.test.mjs). The Bedrock binding is fence_gate.js.
//
// Ported from vanilla Java FenceGateBlock, read from Mojang's 1.21.1 client jar
// (net.minecraft.world.level.block.FenceGateBlock, through Mojang's client.txt; the same
// in 1.20.1 and 1.21.8; pins in portkit/data/wood_types.py):
//   getStateForPlacement -> placed(): open = powered = hasNeighborSignal; in_wall = a
//                           wall on either side across the gate (west/east for a gate
//                           facing north or south, north/south for east or west)
//   updateShape          -> inWall(): recomputed from both sides
//   useWithoutItem       -> use(): an open gate closes; a closed gate opens, first
//                           turning to face the way the player looks when it faced the
//                           player (facing == player.getDirection().getOpposite()), and
//                           the gate's sound plays either way (open or close)
//   neighborChanged      -> powerChange(): only a change of powered moves the gate:
//                           OPEN = POWERED = powered, with the sound when OPEN changes

export const OPPOSITE = { north: "south", south: "north", east: "west", west: "east" };
// Direction#getStepX / getStepZ.
export const STEP = { north: [0, -1], south: [0, 1], west: [-1, 0], east: [1, 0] };

/** The two directions across a gate facing `facing` (where walls lower it). */
export function sides(facing) {
  return facing === "north" || facing === "south" ? ["west", "east"] : ["north", "south"];
}

/** in_wall for a gate facing `facing`; `isWall(direction)` says whether that neighbour is a wall. */
export function inWall(facing, isWall) {
  const [a, b] = sides(facing);
  return Boolean(isWall(a) || isWall(b));
}

/**
 * The horizontal direction an entity looking along `view` ({x, z}) faces
 * (Player#getDirection: Direction.fromYRot, the nearest of the four). A look exactly
 * between two of them counts as north/south here.
 */
export function directionOf(view) {
  const x = view?.x ?? 0;
  const z = view?.z ?? 0;
  if (Math.abs(x) > Math.abs(z)) return x > 0 ? "east" : "west";
  return z > 0 ? "south" : "north";
}

/** The states a gate is placed with (getStateForPlacement), facing set by placement. */
export function placed(powered, wall) {
  return { open: Boolean(powered), powered: Boolean(powered), in_wall: Boolean(wall) };
}

/**
 * What a use does (useWithoutItem): `state` is { facing, open }, `player` the direction
 * the player faces. Returns the new { facing, open } and the sound to play ("open" or
 * "close": Java plays the gate's open sound when it is now open, else its close sound).
 */
export function use(state, player) {
  if (state.open) return { facing: state.facing, open: false, sound: "close" };
  const facing = state.facing === OPPOSITE[player] ? player : state.facing;
  return { facing, open: true, sound: "open" };
}

/**
 * What a change of redstone does (neighborChanged): null when powered doesn't change,
 * else the new { open, powered } and whether the sound plays (when open changes).
 */
export function powerChange(state, powered) {
  if (Boolean(powered) === Boolean(state.powered)) return null;
  return { open: Boolean(powered), powered: Boolean(powered), sound: Boolean(powered) !== Boolean(state.open) };
}

/** A pitch in [lo, hi) from a random number in [0, 1) (Java nextFloat() * 0.1F + 0.9F). */
export function pitch(range, random) {
  const [lo, hi] = range ?? [1, 1];
  return lo + (hi - lo) * random;
}
