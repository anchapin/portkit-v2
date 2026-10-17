// The fixed door runtime (src/portkit/runtime/door.js, door_core.js), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/door_core.test.mjs
// (tests/test_doors.py runs it with PORTKIT_DOOR_TABLE set to a data table the
// converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import { hinge, otherHalf, powerChange, soundFor, use } from "../../src/portkit/runtime/door_core.js";
import { registerDoors } from "../../src/portkit/runtime/door.js";
import { _permutation, _startup } from "@minecraft/server";

const FALLBACK = {
  component: "examplemod:portkit_door",
  states: { hinge: "examplemod:hinge", open: "examplemod:open", powered: "examplemod:powered" },
  doors: {
    "examplemod:oak_door": { hand: true, open_sound: "open.wooden_door", close_sound: "close.wooden_door" },
    "examplemod:iron_door": { hand: false, open_sound: "open.iron_door", close_sound: "close.iron_door" },
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_DOOR_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerDoors(table);
const component = _startup()[table.component];
const S = table.states;
const AIR = { full: false, lowerDoor: false };
const WALL = { full: true, lowerDoor: false };
const DOOR = { full: false, lowerDoor: true };

// -- pure rules (DoorBlock#getHinge, #neighborChanged, #useWithoutItem) ------

test("hinge: walls on the right put the hinge right, on the left left", () => {
  assert.equal(hinge("north", { right: WALL }, null), "right");
  assert.equal(hinge("north", { left: WALL, leftAbove: WALL }, null), "left");
  // Two right, one left: the score is still positive.
  assert.equal(hinge("north", { left: WALL, right: WALL, rightAbove: WALL }, null), "right");
});

test("hinge: a lone door beside it wins over the walls", () => {
  assert.equal(hinge("east", { left: DOOR }, null), "right");
  assert.equal(hinge("east", { right: DOOR }, null), "left");
  // Doors on both sides: falls through to the walls, then the click.
  assert.equal(hinge("east", { left: DOOR, right: DOOR, rightAbove: WALL }, null), "right");
});

test("hinge: with nothing around, the click half decides", () => {
  // Facing north (step z -1): x past the middle is the right hand side.
  assert.equal(hinge("north", {}, { dx: 0.9, dz: 0.5 }), "right");
  assert.equal(hinge("north", {}, { dx: 0.1, dz: 0.5 }), "left");
  assert.equal(hinge("south", {}, { dx: 0.1, dz: 0.5 }), "right");
  assert.equal(hinge("east", {}, { dx: 0.5, dz: 0.9 }), "right");
  assert.equal(hinge("west", {}, { dx: 0.5, dz: 0.1 }), "right");
  // No click (or the exact middle): left, as Java's centre test.
  for (const f of ["north", "east", "south", "west"]) assert.equal(hinge(f, { left: AIR }, null), "left");
});

test("redstone moves the door only on a change of power", () => {
  assert.equal(powerChange({ open: false, powered: false }, false), null);
  assert.deepEqual(powerChange({ open: false, powered: false }, true), { open: true, powered: true, sound: true });
  // Opened by hand, then powered: already open, so no sound.
  assert.deepEqual(powerChange({ open: true, powered: false }, true), { open: true, powered: true, sound: false });
  assert.deepEqual(powerChange({ open: true, powered: true }, false), { open: false, powered: false, sound: true });
  assert.equal(powerChange({ open: true, powered: true }, true), null);
});

test("a hand flips open only on a door a hand opens", () => {
  assert.deepEqual(use({ open: false, powered: true }, true), { open: true, powered: true, sound: true });
  assert.equal(use({ open: false, powered: false }, false), null);
});

test("the other half and the sounds", () => {
  assert.deepEqual(otherHalf(0, { x: 1, y: 64, z: 2 }), { x: 1, y: 65, z: 2 });
  assert.deepEqual(otherHalf(1, { x: 1, y: 65, z: 2 }), { x: 1, y: 64, z: 2 });
  const door = { open_sound: "o", close_sound: "c" };
  assert.equal(soundFor(door, true), "o");
  assert.equal(soundFor(door, false), "c");
});

// -- the runtime on a small world --------------------------------------------

function world() {
  const blocks = new Map();
  const sounds = [];
  const key = (l) => `${l.x},${l.y},${l.z}`;
  const dim = {
    getBlock: (l) => blocks.get(key(l)) ?? { typeId: "minecraft:air", isAir: true, isLiquid: false,
      permutation: _permutation("minecraft:air"), location: l },
    playSound: (id, at) => sounds.push(id),
  };
  function put(typeId, loc, states, power = 0) {
    const block = {
      typeId, location: loc, dimension: dim, isAir: false, isLiquid: false, power,
      permutation: _permutation(typeId, states),
      setPermutation(p) { this.permutation = p; },
      getRedstonePower() { return this.power; },
      center: () => ({ x: loc.x + 0.5, y: loc.y + 0.5, z: loc.z + 0.5 }),
    };
    blocks.set(key(loc), block);
    return block;
  }
  return { dim, put, sounds };
}

function placeDoor(w, typeId, at, facing = "north", extra = {}) {
  const states = { "minecraft:cardinal_direction": facing, [S.hinge]: "left", [S.open]: false, [S.powered]: false, ...extra };
  const lower = w.put(typeId, at, { ...states, "minecraft:multi_block_part": 0 });
  const upper = w.put(typeId, { ...at, y: at.y + 1 }, { ...states, "minecraft:multi_block_part": 1 });
  return { lower, upper };
}

const ids = Object.keys(table.doors);
const handId = ids.find((id) => table.doors[id].hand);
const ironId = ids.find((id) => !table.doors[id].hand);

test("the component has every event the door needs", () => {
  for (const name of ["beforeOnPlayerPlace", "onPlace", "onPlayerInteract", "onRedstoneUpdate"]) {
    assert.equal(typeof component[name], "function", name);
  }
});

test("placing picks the hinge from the wall on the right", () => {
  const w = world();
  const at = { x: 0, y: 64, z: 0 };
  w.put("minecraft:stone", { x: 1, y: 64, z: 0 }, {}); // east of a north-facing door: its right
  const event = {
    block: { location: at }, dimension: w.dim, player: undefined,
    permutationToPlace: _permutation(handId, { "minecraft:cardinal_direction": "north", [S.hinge]: "left" }),
  };
  component.beforeOnPlayerPlace(event);
  assert.equal(event.permutationToPlace.getState(S.hinge), "right");
});

test("a use opens and closes both halves with the door's sounds", () => {
  const w = world();
  const { lower, upper } = placeDoor(w, handId, { x: 0, y: 64, z: 0 });
  component.onPlayerInteract({ block: upper });
  assert.equal(lower.permutation.getState(S.open), true);
  assert.equal(upper.permutation.getState(S.open), true);
  component.onPlayerInteract({ block: lower });
  assert.equal(lower.permutation.getState(S.open), false);
  assert.equal(upper.permutation.getState(S.open), false);
  assert.deepEqual(w.sounds, [table.doors[handId].open_sound, table.doors[handId].close_sound]);
});

test("power opens it, losing power closes it, no change does nothing", () => {
  const w = world();
  const id = ironId ?? handId;
  const { lower, upper } = placeDoor(w, id, { x: 5, y: 64, z: 5 });
  lower.power = 15;
  component.onRedstoneUpdate({ block: lower, powerLevel: 15 });
  for (const b of [lower, upper]) {
    assert.equal(b.permutation.getState(S.open), true);
    assert.equal(b.permutation.getState(S.powered), true);
  }
  component.onRedstoneUpdate({ block: upper, powerLevel: 15 });
  assert.equal(w.sounds.length, 1);
  lower.power = 0;
  component.onRedstoneUpdate({ block: lower, powerLevel: 0 });
  for (const b of [lower, upper]) {
    assert.equal(b.permutation.getState(S.open), false);
    assert.equal(b.permutation.getState(S.powered), false);
  }
  assert.equal(w.sounds.length, 2);
});

test("a door a hand can't open stays shut on a use", { skip: !ironId }, () => {
  const w = world();
  const { lower } = placeDoor(w, ironId, { x: 0, y: 64, z: 0 });
  component.onPlayerInteract({ block: lower });
  assert.equal(lower.permutation.getState(S.open), false);
  assert.deepEqual(w.sounds, []);
});

test("placed already powered, the upper half's onPlace opens it silently", () => {
  const w = world();
  const { lower, upper } = placeDoor(w, handId, { x: 0, y: 64, z: 0 });
  lower.power = 7;
  component.onPlace({ block: lower });
  assert.equal(lower.permutation.getState(S.open), false);
  component.onPlace({ block: upper });
  assert.equal(lower.permutation.getState(S.open), true);
  assert.deepEqual(w.sounds, []);
});
