// The fixed pressure plate runtime (src/portkit/runtime/pressure_plate.js on pressure_plate_core.js), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/pressure_plate.test.mjs
// (tests/test_plates.py runs it with PORTKIT_PLATE_TABLE set to a data table
// the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import { registerPressurePlates } from "../../src/portkit/runtime/pressure_plate.js";
import { inTouchBox, presses, step } from "../../src/portkit/runtime/pressure_plate_core.js";
import { _permutation, _startup, system } from "@minecraft/server";

const FALLBACK = {
  component: "examplemod:portkit_pressure_plate",
  powered: "examplemod:powered",
  pressed_ticks: 20,
  touch: { min: [0.0625, 0, 0.0625], max: [0.9375, 0.25, 0.9375] },
  plates: {
    "examplemod:oak_pressure_plate": {
      mobs_only: false, on_sound: "click_on.wooden_pressure_plate", off_sound: "click_off.wooden_pressure_plate",
      on_pitch: 1, off_pitch: 1,
    },
    "examplemod:stone_pressure_plate": {
      mobs_only: true, on_sound: "click_on.stone_pressure_plate", off_sound: "click_off.stone_pressure_plate",
      on_pitch: 1, off_pitch: 1,
    },
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_PLATE_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerPressurePlates(table);
const component = _startup()[table.component];
const TOUCH = table.touch;

// -- the pure rules ----------------------------------------------------------

test("the touch box is Java's TOUCH_AABB around the plate", () => {
  const at = { x: 10, y: 64, z: -3 };
  assert.ok(inTouchBox(TOUCH, at, { x: 10.5, y: 64, z: -2.5 }));
  assert.ok(inTouchBox(TOUCH, at, { x: 10.0625, y: 64.25, z: -2.0625 }));
  assert.ok(!inTouchBox(TOUCH, at, { x: 10.03, y: 64, z: -2.5 }), "the 1/16 rim");
  assert.ok(!inTouchBox(TOUCH, at, { x: 10.5, y: 64.3, z: -2.5 }), "above 4/16");
  assert.ok(!inTouchBox(TOUCH, at, { x: 11.5, y: 64, z: -2.5 }), "the next block");
});

test("what presses: everything, or mobs and players only; never a spectator", () => {
  const item = { typeId: "minecraft:item", mob: false, spectator: false };
  const pig = { typeId: "minecraft:pig", mob: true, spectator: false };
  const player = { typeId: "minecraft:player", mob: false, spectator: false };
  const ghost = { typeId: "minecraft:player", mob: false, spectator: true };
  assert.equal(presses(item, false), true);
  assert.equal(presses(item, true), false);
  assert.equal(presses(pig, true), true);
  assert.equal(presses(player, true), true);
  assert.equal(presses(ghost, false), false);
});

test("checkPressed: press at once, hold 20 ticks, release at the first empty re-check", () => {
  assert.deepEqual(step(false, false, 100, undefined, 20), { powered: false, sound: null, due: undefined });
  assert.deepEqual(step(false, true, 100, undefined, 20), { powered: true, sound: "on", due: 120 });
  // pressed, re-check not due: nothing happens whoever is there
  assert.deepEqual(step(true, false, 110, 120, 20), { powered: true, sound: null, due: 120 });
  // due and still pressed: hold another 20
  assert.deepEqual(step(true, true, 120, 120, 20), { powered: true, sound: null, due: 140 });
  // due and empty: release
  assert.deepEqual(step(true, false, 141, 140, 20), { powered: false, sound: "off", due: undefined });
  // after a reload (no due tick) a pressed plate checks now
  assert.deepEqual(step(true, false, 5, undefined, 20), { powered: false, sound: "off", due: undefined });
});

// -- the binding -------------------------------------------------------------

function world(entities) {
  const sounds = [];
  const dim = {
    id: "minecraft:overworld",
    playSound: (id, _loc, opts) => sounds.push([id, opts?.pitch]),
    getEntities: () => entities,
  };
  function put(typeId, loc, powered = false) {
    return {
      typeId, location: loc, dimension: dim,
      permutation: _permutation(typeId, { [table.powered]: powered }),
      setPermutation(p) { this.permutation = p; },
      center: () => ({ x: loc.x + 0.5, y: loc.y + 0.5, z: loc.z + 0.5 }),
    };
  }
  return { put, sounds };
}

const ids = Object.keys(table.plates);
const anyId = ids.find((id) => !table.plates[id].mobs_only);
const powered = (b) => b.permutation.getState(table.powered);

function entity(typeId, loc, mob) {
  return { typeId, location: loc, matches: () => mob, getGameMode: () => "Survival" };
}

test("the component ticks, and nothing else", () => {
  assert.equal(typeof component.onTick, "function");
  assert.equal(component.onStepOn, undefined);
});

test("an item presses an everything plate; it releases 20 ticks after the item goes", () => {
  const at = { x: 0, y: 64, z: 0 };
  const things = [entity("minecraft:item", { x: 0.5, y: 64, z: 0.5 }, false)];
  const w = world(things);
  const plate = w.put(anyId, at);
  system.currentTick = 1000;
  component.onTick({ block: plate });
  assert.equal(powered(plate), true);
  assert.equal(w.sounds[0][0], table.plates[anyId].on_sound);
  things.length = 0;
  system.currentTick = 1010;
  component.onTick({ block: plate });
  assert.equal(powered(plate), true, "held until the re-check");
  system.currentTick = 1020;
  component.onTick({ block: plate });
  assert.equal(powered(plate), false);
  assert.equal(w.sounds[1][0], table.plates[anyId].off_sound);
});

test("an entity outside the touch box presses nothing", () => {
  const w = world([entity("minecraft:pig", { x: 1.2, y: 64, z: 0.5 }, true)]);
  const plate = w.put(anyId, { x: 0, y: 64, z: 0 });
  system.currentTick = 2000;
  component.onTick({ block: plate });
  assert.equal(powered(plate), false);
  assert.deepEqual(w.sounds, []);
});

test("a mobs-only plate ignores an item and takes a mob", { skip: !ids.some((id) => table.plates[id].mobs_only) }, () => {
  const mobsId = ids.find((id) => table.plates[id].mobs_only);
  const things = [entity("minecraft:item", { x: 0.5, y: 64, z: 0.5 }, false)];
  const w = world(things);
  const plate = w.put(mobsId, { x: 0, y: 64, z: 0 });
  system.currentTick = 3000;
  component.onTick({ block: plate });
  assert.equal(powered(plate), false);
  things.push(entity("minecraft:zombie", { x: 0.4, y: 64, z: 0.6 }, true));
  component.onTick({ block: plate });
  assert.equal(powered(plate), true);
});

test("a block that is no longer a plate is left alone", () => {
  const w = world([entity("minecraft:item", { x: 0.5, y: 64, z: 0.5 }, false)]);
  const air = w.put("minecraft:air", { x: 0, y: 64, z: 0 });
  component.onTick({ block: air });
  assert.equal(air.permutation.getState(table.powered), false);
});
