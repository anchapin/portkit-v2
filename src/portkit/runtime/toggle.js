// portkit runtime: a boolean block state that using the block flips.
//
// Fixed file, copied verbatim into every pack with such a block
// (portkit/runtime/; see docs/decisions.md, 2026-10-14 facing and boolean
// blocks). The generated entry scripts/portkit/main.js calls
// registerToggles(table) with the mod's data table: the custom component
// name and, per block id, the Bedrock state it flips. A block is in the
// table only when its Java useWithoutItem was read from bytecode to put the
// block back with that one boolean flipped on every way through it
// (Level#setBlock(pos, state.cycle(P)) or setValue(P, !getValue(P)), on the
// server), and its classes don't override useItemOn (portkit.blockcode
// read_state_blocks). Nothing else Java's method does (a sound, particles,
// a game event) is carried.
//
// Script API: @minecraft/server 2.0.0 (Bedrock 1.21.90), custom components
// v2 (BlockCustomComponent onPlayerInteract).

import { system } from "@minecraft/server";

/** The permutation after a use: the table's state flipped, or null. */
export function flipped(table, block) {
  const state = table.blocks[block.typeId];
  if (!state) return null;
  const value = block.permutation.getState(state);
  if (typeof value !== "boolean") return null;
  return block.permutation.withState(state, !value);
}

/** Register the toggle custom component for one mod's data table. */
export function registerToggles(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onPlayerInteract: (event) => {
        const next = flipped(table, event.block);
        if (next) event.block.setPermutation(next);
      },
    });
  });
}
