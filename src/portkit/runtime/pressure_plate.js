// portkit runtime: pressure plates (#296).
// portkit-requires: @minecraft/server 2.0.0
//
// Fixed file, copied verbatim into every pack with a converted pressure plate
// (portkit/runtime/; docs/decisions.md 2026-10-17 pressure plates). The
// generated entry scripts/portkit/main.js calls registerPressurePlates(table)
// with the mod's table: the custom component, the `powered` state, Java's
// pressed time and touch box, and per plate id whether only mobs press it and
// its click sounds. The rules are pressure_plate_core.js's.
//
// Bedrock's onStepOn/onStepOff need a collision box taller than 3.2 pixels
// (Bedrock Wiki, Block Events) and a plate has no collision, so the block's
// minecraft:tick sends onTick every few ticks and the plate looks for
// entities itself. Its minecraft:redstone_producer gives power 15 on the
// powered permutation (fixed for permutation changes in 1.21.130,
// MCPE-229570). Script API @minecraft/server 2.0.0 (custom components v2:
// onTick; Dimension.getEntities, Entity.matches).

import { system } from "@minecraft/server";
import { inTouchBox, presses, step } from "./pressure_plate_core.js";

// When each pressed plate's next re-check is due, by place. Lost on a reload:
// a pressed plate with no entry re-checks at once (see step()).
const due = new Map();

function key(block) {
  const { x, y, z } = block.location;
  return `${block.dimension.id}|${x},${y},${z}`;
}

function describeEntity(entity) {
  let spectator = false;
  let mob = false;
  try {
    if (entity.typeId === "minecraft:player") {
      spectator = String(entity.getGameMode?.() ?? "").toLowerCase() === "spectator";
    }
    mob = entity.matches?.({ families: ["mob"] }) === true;
  } catch {
    // an entity that went away mid-look presses nothing
    return { typeId: entity.typeId, mob: false, spectator: true };
  }
  return { typeId: entity.typeId, mob, spectator };
}

function pressed(table, plate, block) {
  const at = block.location;
  const centre = { x: at.x + 0.5, y: at.y, z: at.z + 0.5 };
  let found;
  try {
    found = block.dimension.getEntities({ location: centre, maxDistance: 1.5 });
  } catch {
    return false;
  }
  return found.some((e) => {
    try {
      return inTouchBox(table.touch, at, e.location) && presses(describeEntity(e), plate.mobs_only);
    } catch {
      return false;
    }
  });
}

function stillPlate(table, block) {
  try {
    return block.isValid !== false && table.plates[block.typeId] !== undefined;
  } catch {
    return false;
  }
}

/** Register the pressure plate custom component for one mod's table. */
export function registerPressurePlates(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onTick: (event) => {
        const block = event.block;
        if (!stillPlate(table, block)) return;
        const plate = table.plates[block.typeId];
        const where = key(block);
        const powered = block.permutation.getState(table.powered) === true;
        const now = system.currentTick ?? 0;
        // A pressed plate looks only when its re-check is due.
        const wanted = due.get(where);
        const present = powered && wanted !== undefined && now < wanted ? true : pressed(table, plate, block);
        const next = step(powered, present, now, wanted, table.pressed_ticks);
        if (next.due === undefined) due.delete(where);
        else due.set(where, next.due);
        if (next.powered === powered) return;
        block.setPermutation(block.permutation.withState(table.powered, next.powered));
        try {
          const sound = next.sound === "on" ? plate.on_sound : plate.off_sound;
          const pitch = next.sound === "on" ? plate.on_pitch : plate.off_pitch;
          block.dimension.playSound(sound, block.center(), { pitch });
        } catch {
          // a sound the client doesn't know is not an error worth failing a press
        }
      },
    });
  });
}
