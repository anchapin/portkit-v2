// portkit station kit: pure helpers every scripted station shares (#245).
//
// Fixed file, copied verbatim into every pack that ships a station runtime
// (portkit/runtime/; see docs/decisions.md, 2026-10-13 and 2026-10-15). It
// names no mod and imports nothing, so node tests it offline
// (tests/js/station_core.test.mjs). The Bedrock-side helpers are
// station_storage.js; the form helper is forms.js.
//
// Each piece was a copy inside a mod's runtime before #245 and keeps that
// code's behaviour exactly: the storage key (four *_core.js copies), the
// counter-clockwise side step (cooking pot and cutting board), the heat rule
// (cooking pot, read by the skillet too), the destroy command (feasts and
// Waystones) and the held-item use timer (Waystones' scrolls and warp stone).

/** The dynamic-property key holding a station's state at this position. */
export function storageKey(component, dimensionId, location) {
  return `${component}|${dimensionId}|${location.x},${location.y},${location.z}`;
}

/** The prefix every storageKey of `component` starts with (to list a station's records). */
export function storagePrefix(component) {
  return `${component}|`;
}

const COUNTER_CLOCKWISE = { north: "west", west: "south", south: "east", east: "north" };
const STEP = { north: [0, -1], south: [0, 1], west: [-1, 0], east: [1, 0] };

/**
 * The unit [x, z] step toward `facing` turned counter-clockwise (Java's
 * Direction#getCounterClockWise); an unknown facing counts as north (west).
 */
export function counterClockwiseStep(facing) {
  return STEP[COUNTER_CLOCKWISE[facing] ?? "west"];
}

/** Whether a block ({ id, state(name) }) matches one heat rule of the table. */
export function blockMatches(rule, block) {
  if (!block || block.id !== rule.id) return false;
  for (const [name, value] of Object.entries(rule.states ?? {})) {
    if (block.state(name) !== value) return false;
  }
  for (const [name, value] of Object.entries(rule.not ?? {})) {
    if (block.state(name) === value) return false;
  }
  return true;
}

/**
 * The heat rule (Farmer's Delight HeatableBlockEntity#isHeated, L19-38): the
 * block below is a heat source (lit, if it can be unlit), or a heat conductor
 * with a heat source below it. `heat` is the table's { sources, conductors }.
 */
export function isHeated(heat, below, belowTwo) {
  if (heat.sources.some((r) => blockMatches(r, below))) return true;
  if (heat.conductors.some((r) => blockMatches(r, below))) {
    return heat.sources.some((r) => blockMatches(r, belowTwo));
  }
  return false;
}

/** Tray over a tray heat source, else none (Farmer's Delight CookingPotBlock#getTrayState, L137-142). */
export function trayState(heat, below) {
  return heat.tray.some((r) => blockMatches(r, below)) ? "tray" : "none";
}

/** `setblock` that removes the block at `location` and drops its loot (Java's destroyBlock with drops). */
export function destroyCommand(location) {
  return `setblock ${location.x} ${location.y} ${location.z} air destroy`;
}

/**
 * Items held in use for a use time (Java's LivingEntity#startUsingItem /
 * updatingUsingItem / finishUsingItem), one per player id. `start` begins a
 * hold; `tick(heldAt, done)` stands for one game tick: a hold whose player is
 * gone, or who switched slots or no longer holds that item in it, stops; one
 * that reaches its use time stops and calls `done(hold)`. A script can't see
 * the use button released, so letting go does not stop a hold; the binding
 * stops one on a hit (`stop`).
 */
export class HoldTimer {
  constructor() {
    this.holds = new Map();
  }

  has(id) {
    return this.holds.has(id);
  }

  start(player, slot, typeId, useTime) {
    this.holds.set(player.id, { player, slot, typeId, ticks: 0, useTime });
  }

  stop(id) {
    this.holds.delete(id);
  }

  tick(heldAt, done) {
    for (const [id, c] of this.holds) {
      const player = c.player;
      if (!player || (player.isValid !== undefined && !player.isValid)) {
        this.holds.delete(id);
        continue;
      }
      const held = heldAt(player, c.slot);
      if (player.selectedSlotIndex !== c.slot || !held || held.typeId !== c.typeId) {
        this.holds.delete(id);
        continue;
      }
      c.ticks += 1;
      if (c.ticks >= c.useTime) {
        this.holds.delete(id);
        done(c);
      }
    }
  }
}
