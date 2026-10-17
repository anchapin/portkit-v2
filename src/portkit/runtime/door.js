// portkit runtime: doors on Bedrock's multi_block trait (#296).
// portkit-requires: @minecraft/server 2.5.0
//
// Fixed file, copied verbatim into every pack with a converted door
// (portkit/runtime/; docs/decisions.md 2026-10-17 doors). The generated entry
// scripts/portkit/main.js calls registerDoors(table) with the mod's table:
// the custom component, the three custom states and, per door id, whether a
// hand opens it and its open/close sounds. The rules are door_core.js.
//
// Script API @minecraft/server 2.5.0 (Bedrock 1.26.0): custom components v2
// (BlockCustomComponent beforeOnPlayerPlace, onPlace, onPlayerInteract,
// onRedstoneUpdate; onRedstoneUpdate is first in the 2.5.0 stable typings).
// The block's minecraft:redstone_consumer (min_power 0) sends every redstone
// update. Bedrock keeps the halves together (minecraft:multi_block): part 0
// is the lower half, every state but the part must match, so a change is
// written to both parts.
//
// Approximations (the notes say so per door): Java's "collision shape is a
// full block" test for the hinge is "not air, not liquid, not a door" here
// (the Script API has no collision query); the click point is the player's
// view ray on the clicked face (getBlockFromViewDirection), as Java's
// getClickLocation.

import { system } from "@minecraft/server";
import { hinge, otherHalf, powerChange, soundFor, use } from "./door_core.js";

const PART = "minecraft:multi_block_part";
const FACING = "minecraft:cardinal_direction";

function isDoor(table, block) {
  return !!block && (table.doors[block.typeId] !== undefined || block.typeId.endsWith("_door"));
}

function lowerDoor(table, block) {
  if (!isDoor(table, block)) return false;
  const perm = block.permutation;
  if (table.doors[block.typeId] !== undefined) return perm.getState(PART) === 0;
  // Vanilla Bedrock doors: upper_block_bit false is the lower half.
  return perm.getState("upper_block_bit") === false;
}

function neighbour(table, dim, loc) {
  let block;
  try {
    block = dim.getBlock(loc);
  } catch {
    block = undefined;
  }
  if (!block) return { full: false, lowerDoor: false };
  return {
    full: !block.isAir && !block.isLiquid && !isDoor(table, block),
    lowerDoor: lowerDoor(table, block),
  };
}

const STEP = { north: [0, -1], south: [0, 1], west: [-1, 0], east: [1, 0] };
const CCW = { north: "west", west: "south", south: "east", east: "north" };
const CW = { north: "east", east: "south", south: "west", west: "north" };

function nearOf(table, dim, loc, facing) {
  const at = (dir, dy) => ({ x: loc.x + STEP[dir][0], y: loc.y + dy, z: loc.z + STEP[dir][1] });
  return {
    left: neighbour(table, dim, at(CCW[facing], 0)),
    leftAbove: neighbour(table, dim, at(CCW[facing], 1)),
    right: neighbour(table, dim, at(CW[facing], 0)),
    rightAbove: neighbour(table, dim, at(CW[facing], 1)),
  };
}

function clickOf(player, loc) {
  try {
    const hit = player?.getBlockFromViewDirection({ maxDistance: 8 });
    if (!hit) return null;
    const x = hit.block.location.x + hit.faceLocation.x;
    const z = hit.block.location.z + hit.faceLocation.z;
    return { dx: x - loc.x, dz: z - loc.z };
  } catch {
    return null;
  }
}

function stateOf(table, block) {
  const perm = block.permutation;
  return { open: perm.getState(table.states.open), powered: perm.getState(table.states.powered) };
}

function parts(block) {
  const part = block.permutation.getState(PART);
  let other;
  try {
    other = block.dimension.getBlock(otherHalf(part, block.location));
  } catch {
    other = undefined;
  }
  const both = [block];
  if (other && other.typeId === block.typeId) both.push(other);
  return both;
}

function apply(table, block, next) {
  for (const b of parts(block)) {
    b.setPermutation(b.permutation
      .withState(table.states.open, next.open)
      .withState(table.states.powered, next.powered));
  }
  if (next.sound) {
    const door = table.doors[block.typeId];
    try {
      block.dimension.playSound(soundFor(door, next.open), block.center());
    } catch {
      // a sound the client doesn't know is not an error worth failing a use
    }
  }
}

function powerOf(block) {
  let power = 0;
  for (const b of parts(block)) {
    try {
      power = Math.max(power, b.getRedstonePower() ?? 0);
    } catch {
      // no power reading here
    }
  }
  return power;
}

/** Register the door custom component for one mod's table. */
export function registerDoors(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      beforeOnPlayerPlace: (event) => {
        const perm = event.permutationToPlace;
        const facing = perm.getState(FACING) ?? "south";
        const loc = event.block.location;
        const side = hinge(facing, nearOf(table, event.dimension, loc, facing), clickOf(event.player, loc));
        event.permutationToPlace = perm.withState(table.states.hinge, side);
      },
      onPlace: (event) => {
        // Java places a door open when it is powered already; the last part
        // placed (the upper half) reads both.
        if (event.block.permutation.getState(PART) !== 1) return;
        const next = powerChange(stateOf(table, event.block), powerOf(event.block) > 0);
        if (next) apply(table, event.block, { ...next, sound: false });
      },
      onPlayerInteract: (event) => {
        const door = table.doors[event.block.typeId];
        if (!door) return;
        const next = use(stateOf(table, event.block), door.hand);
        if (next) apply(table, event.block, next);
      },
      onRedstoneUpdate: (event) => {
        const power = Math.max(event.powerLevel ?? 0, powerOf(event.block));
        const next = powerChange(stateOf(table, event.block), power > 0);
        if (next) apply(table, event.block, next);
      },
    });
  });
}
