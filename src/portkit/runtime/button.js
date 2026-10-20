// portkit runtime: buttons (#280).
// portkit-requires: @minecraft/server 2.0.0
//
// Fixed file, copied verbatim into every pack with a converted button
// (portkit/runtime/; docs/decisions.md 2026-10-20 buttons). The generated
// entry scripts/portkit/main.js calls registerButtons(table) with the mod's
// table: the custom component, the `powered` state, the scriptevent id that
// presses a button, and per button id its press time in ticks, whether
// arrows press it and its click sounds. The rules are button_core.js's.
//
// The block's minecraft:redstone_producer gives power 15 on the powered
// permutations (strongly into the block it hangs on), so the runtime only
// flips `powered`: a player's use (custom component onPlayerInteract), an
// arrow or trident hitting it (world.afterEvents.projectileHitBlock), or
// `/scriptevent portkit:button_press <x> <y> <z>` (the same press a use
// takes, for command blocks and the in-game check) press it; the release is
// a system.runTimeout of the press time, as Java's scheduled tick. A reload
// drops the timer: the block's minecraft:tick (every press time) releases a
// powered button with none. Script API @minecraft/server 2.0.0 (custom
// components v2: onPlayerInteract, onTick).

import { system, world } from "@minecraft/server";
import { arrowHit, check, inCell, use } from "./button_core.js";

// Java's AbstractArrow on Bedrock: arrows (spectral ones are arrows) and tridents.
const ARROWS = ["minecraft:arrow", "minecraft:thrown_trident"];
// The release due at each place, by place; a newer schedule replaces it.
const due = new Map();

function key(dimension, at) {
  return `${dimension.id}|${at.x},${at.y},${at.z}`;
}

function arrowInside(block) {
  try {
    const at = block.location;
    return block.dimension.getEntities({ location: block.center(), maxDistance: 1.5 })
      .some((e) => ARROWS.includes(e.typeId) && inCell(at, e.location, 0.1));
  } catch {
    return false;
  }
}

function row(table, block) {
  try {
    return block.isValid !== false ? table.buttons[block.typeId] : undefined;
  } catch {
    return undefined;
  }
}

function apply(table, block, button, next) {
  if (next === null) return;
  const powered = block.permutation.getState(table.powered) === true;
  if (next.powered !== powered) block.setPermutation(block.permutation.withState(table.powered, next.powered));
  if (next.sound !== null) {
    try {
      const on = next.sound === "on";
      block.dimension.playSound(on ? button.on_sound : button.off_sound, block.center(),
        { pitch: on ? button.on_pitch : button.off_pitch });
    } catch {
      // a sound the client doesn't know is not worth failing a press
    }
  }
  if (next.schedule) schedule(table, block.dimension, block.location, next.schedule);
}

function schedule(table, dimension, at, ticks) {
  const where = key(dimension, at);
  const when = (system.currentTick ?? 0) + ticks;
  due.set(where, when);
  system.runTimeout(() => {
    if (due.get(where) !== when) return;
    due.delete(where);
    release(table, dimension, at);
  }, ticks);
}

// Java's tick: a powered button runs checkPressed.
function release(table, dimension, at) {
  let block;
  try {
    block = dimension.getBlock(at);
  } catch {
    return;
  }
  const button = block && row(table, block);
  if (!button || block.permutation.getState(table.powered) !== true) return;
  apply(table, block, button, check(true, button.arrows && arrowInside(block), button.arrows, button.ticks));
}

function press(table, block) {
  const button = block && row(table, block);
  if (!button) return;
  apply(table, block, button, use(block.permutation.getState(table.powered) === true, button.ticks));
}

/** Register the button custom component and events for one mod's table. */
export function registerButtons(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onPlayerInteract: (event) => press(table, event.block),
      onTick: (event) => {
        const block = event.block;
        if (!row(table, block) || block.permutation.getState(table.powered) !== true) return;
        if (!due.has(key(block.dimension, block.location))) release(table, block.dimension, block.location);
      },
    });
  });
  world.afterEvents.projectileHitBlock.subscribe((event) => {
    try {
      if (!ARROWS.includes(event.projectile?.typeId)) return;
      const block = event.getBlockHit().block;
      const button = row(table, block);
      if (!button) return;
      apply(table, block, button, arrowHit(block.permutation.getState(table.powered) === true, button.arrows,
        button.ticks));
    } catch {
      // a projectile or block that went away mid-event presses nothing
    }
  });
  system.afterEvents.scriptEventReceive.subscribe((event) => {
    if (event.id !== table.press_event) return;
    const parts = String(event.message ?? "").trim().split(/\s+/).map(Number);
    if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return;
    const dimension = event.sourceEntity?.dimension ?? event.sourceBlock?.dimension ?? world.getDimension("overworld");
    try {
      press(table, dimension.getBlock({ x: parts[0], y: parts[1], z: parts[2] }));
    } catch {
      // an unloaded place presses nothing
    }
  });
}
