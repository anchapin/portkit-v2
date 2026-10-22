// portkit runtime: fence gates (#367).
// portkit-requires: @minecraft/server 2.5.0
//
// Fixed file, copied verbatim into every pack with a converted fence gate
// (portkit/runtime/; docs/decisions.md 2026-10-22 fence gates). The generated entry
// scripts/portkit/main.js calls registerFenceGates(table) with the mod's table: the custom
// component, the three custom states, the use scriptevent, the sound pitch range, the
// block ids that count as walls and, per gate id, its open/close sounds. The rules are
// fence_gate_core.js's (vanilla Java FenceGateBlock).
//
// Script API @minecraft/server 2.5.0 (Bedrock 1.26.0): custom components v2
// (BlockCustomComponent onPlace, onPlayerInteract, onRedstoneUpdate; the last is first in
// the 2.5.0 stable typings), the block's minecraft:redstone_consumer (min_power 0) sending
// every redstone update. A custom block's neighbour hook (onNeighborChanged) is still
// pre-release, so in_wall follows the stable world.afterEvents.playerPlaceBlock,
// playerBreakBlock and blockExplode next to a gate (not commands or pistons).
//
// `/scriptevent portkit:fence_gate_use <x> <y> <z> <north|east|south|west>` uses the gate
// at x y z as a player facing that way would: the same path a player's use takes, for
// command blocks and the in-game check (a server with no player).

import { system, world } from "@minecraft/server";
import { STEP, directionOf, inWall, pitch, placed, powerChange, use } from "./fence_gate_core.js";

const CARDINAL = "minecraft:cardinal_direction";
const DIRECTIONS = ["north", "east", "south", "west"];

// The event's block is a place, read when the handler runs: a gate removed in the same
// tick reads as what replaced it (see door.js).
function isGate(table, block) {
  try {
    return block !== undefined && block.isValid !== false && table.gates[block.typeId] !== undefined;
  } catch {
    return false;
  }
}

function stateOf(table, block) {
  const perm = block.permutation;
  return {
    facing: perm.getState(CARDINAL),
    open: perm.getState(table.states.open),
    powered: perm.getState(table.states.powered),
    in_wall: perm.getState(table.states.in_wall),
  };
}

function neighbour(block, direction) {
  const [dx, dz] = STEP[direction];
  try {
    return block.dimension.getBlock({ x: block.location.x + dx, y: block.location.y, z: block.location.z + dz });
  } catch {
    return undefined;
  }
}

function wallTest(table, block) {
  return (direction) => {
    const next = neighbour(block, direction);
    try {
      return next !== undefined && table.walls.includes(next.typeId);
    } catch {
      return false;
    }
  };
}

function write(block, changes) {
  let perm = block.permutation;
  for (const [name, value] of changes) perm = perm.withState(name, value);
  block.setPermutation(perm);
}

function sound(table, block, open) {
  const gate = table.gates[block.typeId];
  try {
    block.dimension.playSound(open ? gate.open_sound : gate.close_sound, block.center(),
      { pitch: pitch(table.pitch, Math.random()) });
  } catch {
    // a sound the client doesn't know is not an error worth failing a use
  }
}

function powerOf(block) {
  try {
    return block.getRedstonePower() ?? 0;
  } catch {
    return 0;
  }
}

function useGate(table, block, playerDirection) {
  if (!isGate(table, block)) return;
  const now = stateOf(table, block);
  const next = use(now, playerDirection);
  write(block, [[CARDINAL, next.facing], [table.states.open, next.open]]);
  sound(table, block, next.open);
}

function refreshWall(table, block) {
  if (!isGate(table, block)) return;
  const now = stateOf(table, block);
  const wall = inWall(now.facing, wallTest(table, block));
  if (wall !== now.in_wall) write(block, [[table.states.in_wall, wall]]);
}

function refreshAround(table, dimension, location) {
  for (const direction of DIRECTIONS) {
    const [dx, dz] = STEP[direction];
    try {
      refreshWall(table, dimension.getBlock({ x: location.x + dx, y: location.y, z: location.z + dz }));
    } catch {
      // an unloaded place has no gate to update
    }
  }
}

/** Register the fence gate custom component for one mod's table. */
export function registerFenceGates(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onPlace: (event) => {
        const block = event.block;
        if (!isGate(table, block)) return;
        const now = stateOf(table, block);
        const next = placed(powerOf(block) > 0, inWall(now.facing, wallTest(table, block)));
        if (next.open !== now.open || next.powered !== now.powered || next.in_wall !== now.in_wall) {
          write(block, [[table.states.open, next.open], [table.states.powered, next.powered],
            [table.states.in_wall, next.in_wall]]);
        }
      },
      onPlayerInteract: (event) => {
        if (!event.player) return;
        useGate(table, event.block, directionOf(event.player.getViewDirection()));
      },
      onRedstoneUpdate: (event) => {
        const block = event.block;
        if (!isGate(table, block)) return;
        const power = Math.max(event.powerLevel ?? 0, powerOf(block));
        const next = powerChange(stateOf(table, block), power > 0);
        if (!next) return;
        write(block, [[table.states.open, next.open], [table.states.powered, next.powered]]);
        if (next.sound) sound(table, block, next.open);
      },
    });
  });
  world.afterEvents.playerPlaceBlock.subscribe((event) => {
    refreshAround(table, event.block.dimension, event.block.location);
  });
  world.afterEvents.playerBreakBlock.subscribe((event) => {
    refreshAround(table, event.block.dimension, event.block.location);
  });
  world.afterEvents.blockExplode.subscribe((event) => {
    refreshAround(table, event.dimension, event.block.location);
  });
  system.afterEvents.scriptEventReceive.subscribe((event) => {
    if (event.id !== table.event) return;
    const parts = String(event.message ?? "").trim().split(/\s+/);
    if (parts.length !== 4 || !DIRECTIONS.includes(parts[3])) return;
    const at = parts.slice(0, 3).map(Number);
    if (at.some((n) => !Number.isFinite(n))) return;
    const dimension = event.sourceEntity?.dimension ?? event.sourceBlock?.dimension ?? world.getDimension("overworld");
    try {
      useGate(table, dimension.getBlock({ x: at[0], y: at[1], z: at[2] }), parts[3]);
    } catch {
      // an unloaded place uses nothing
    }
  });
}
