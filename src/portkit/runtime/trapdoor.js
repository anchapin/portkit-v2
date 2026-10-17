// portkit runtime: trapdoors (#296).
// portkit-requires: @minecraft/server 2.5.0
//
// Fixed file, copied verbatim into every pack with a converted trapdoor
// (portkit/runtime/; docs/decisions.md 2026-10-17 trapdoors). The generated
// entry scripts/portkit/main.js calls registerTrapdoors(table) with the mod's
// table: the custom component, the two custom states and, per trapdoor id,
// whether a hand opens it and its open/close sounds. The rules are
// door_core.js's: vanilla Java TrapDoorBlock#useWithoutItem and
// #neighborChanged (1.21.1) are DoorBlock's for one block (a hand toggles
// OPEN only when BlockSetType#canOpenByHand; a change of neighbour signal sets
// OPEN = POWERED = powered, with the sound when OPEN changes; placed open when
// already powered, getStateForPlacement).
//
// Script API @minecraft/server 2.5.0 (Bedrock 1.26.0): custom components v2
// (BlockCustomComponent onPlace, onPlayerInteract, onRedstoneUpdate; the last
// is first in the 2.5.0 stable typings). The block's
// minecraft:redstone_consumer (min_power 0) sends every redstone update.

import { system } from "@minecraft/server";
import { powerChange, soundFor, use } from "./door_core.js";

// The event's block is a place, read when the handler runs: a trapdoor
// removed in the same tick reads as what replaced it (see door.js).
function stillTrapdoor(table, block) {
  try {
    return block.isValid !== false && table.trapdoors[block.typeId] !== undefined;
  } catch {
    return false;
  }
}

function stateOf(table, block) {
  const perm = block.permutation;
  return { open: perm.getState(table.states.open), powered: perm.getState(table.states.powered) };
}

function apply(table, block, next) {
  block.setPermutation(block.permutation
    .withState(table.states.open, next.open)
    .withState(table.states.powered, next.powered));
  if (next.sound) {
    try {
      block.dimension.playSound(soundFor(table.trapdoors[block.typeId], next.open), block.center());
    } catch {
      // a sound the client doesn't know is not an error worth failing a use
    }
  }
}

function powerOf(block) {
  try {
    return block.getRedstonePower() ?? 0;
  } catch {
    return 0;
  }
}

/** Register the trapdoor custom component for one mod's table. */
export function registerTrapdoors(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onPlace: (event) => {
        if (!stillTrapdoor(table, event.block)) return;
        const next = powerChange(stateOf(table, event.block), powerOf(event.block) > 0);
        if (next) apply(table, event.block, { ...next, sound: false });
      },
      onPlayerInteract: (event) => {
        if (!stillTrapdoor(table, event.block)) return;
        const next = use(stateOf(table, event.block), table.trapdoors[event.block.typeId].hand);
        if (next) apply(table, event.block, next);
      },
      onRedstoneUpdate: (event) => {
        if (!stillTrapdoor(table, event.block)) return;
        const power = Math.max(event.powerLevel ?? 0, powerOf(event.block));
        const next = powerChange(stateOf(table, event.block), power > 0);
        if (next) apply(table, event.block, next);
      },
    });
  });
}
