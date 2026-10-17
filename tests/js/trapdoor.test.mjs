// The fixed trapdoor runtime (src/portkit/runtime/trapdoor.js on door_core.js), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/trapdoor.test.mjs
// (tests/test_trapdoors.py runs it with PORTKIT_TRAPDOOR_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import { registerTrapdoors } from "../../src/portkit/runtime/trapdoor.js";
import { _permutation, _startup } from "@minecraft/server";

const FALLBACK = {
  component: "examplemod:portkit_trapdoor",
  states: { open: "examplemod:open", powered: "examplemod:powered" },
  trapdoors: {
    "examplemod:oak_trapdoor": { hand: true, open_sound: "open.wooden_trapdoor", close_sound: "close.wooden_trapdoor" },
    "examplemod:iron_trapdoor": { hand: false, open_sound: "open.iron_trapdoor", close_sound: "close.iron_trapdoor" },
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_TRAPDOOR_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerTrapdoors(table);
const component = _startup()[table.component];
const S = table.states;

function world() {
  const sounds = [];
  const dim = { playSound: (id) => sounds.push(id) };
  function put(typeId, loc, states = {}, power = 0) {
    return {
      typeId, location: loc, dimension: dim, power,
      permutation: _permutation(typeId, {
        "minecraft:cardinal_direction": "south", "minecraft:vertical_half": "bottom",
        [S.open]: false, [S.powered]: false, ...states,
      }),
      setPermutation(p) { this.permutation = p; },
      getRedstonePower() { return this.power; },
      center: () => ({ x: loc.x + 0.5, y: loc.y + 0.5, z: loc.z + 0.5 }),
    };
  }
  return { put, sounds };
}

const ids = Object.keys(table.trapdoors);
const handId = ids.find((id) => table.trapdoors[id].hand);
const ironId = ids.find((id) => !table.trapdoors[id].hand);
const at = { x: 0, y: 64, z: 0 };
const state = (b) => ({ open: b.permutation.getState(S.open), powered: b.permutation.getState(S.powered) });

test("the component has the events a trapdoor needs, and no placement hook", () => {
  for (const name of ["onPlace", "onPlayerInteract", "onRedstoneUpdate"]) {
    assert.equal(typeof component[name], "function", name);
  }
  assert.equal(component.beforeOnPlayerPlace, undefined);
});

test("a use opens and closes it with its sounds, keeping vertical_half and facing", () => {
  const w = world();
  const b = w.put(handId, at, { "minecraft:vertical_half": "top", "minecraft:cardinal_direction": "east" });
  component.onPlayerInteract({ block: b });
  assert.deepEqual(state(b), { open: true, powered: false });
  assert.equal(b.permutation.getState("minecraft:vertical_half"), "top");
  assert.equal(b.permutation.getState("minecraft:cardinal_direction"), "east");
  component.onPlayerInteract({ block: b });
  assert.deepEqual(state(b), { open: false, powered: false });
  assert.deepEqual(w.sounds, [table.trapdoors[handId].open_sound, table.trapdoors[handId].close_sound]);
});

test("power opens it, losing power closes it, a repeat changes nothing", () => {
  const w = world();
  const b = w.put(ironId ?? handId, at);
  b.power = 15;
  component.onRedstoneUpdate({ block: b, powerLevel: 15 });
  assert.deepEqual(state(b), { open: true, powered: true });
  component.onRedstoneUpdate({ block: b, powerLevel: 15 });
  assert.equal(w.sounds.length, 1);
  b.power = 0;
  component.onRedstoneUpdate({ block: b, powerLevel: 0 });
  assert.deepEqual(state(b), { open: false, powered: false });
  assert.equal(w.sounds.length, 2);
});

test("opened by hand then powered: stays open, silently (TrapDoorBlock#neighborChanged)", () => {
  const w = world();
  const b = w.put(handId, at);
  component.onPlayerInteract({ block: b });
  b.power = 5;
  component.onRedstoneUpdate({ block: b, powerLevel: 5 });
  assert.deepEqual(state(b), { open: true, powered: true });
  assert.equal(w.sounds.length, 1);
});

test("a trapdoor a hand can't open stays shut on a use", { skip: !ironId }, () => {
  const w = world();
  const b = w.put(ironId, at);
  component.onPlayerInteract({ block: b });
  assert.deepEqual(state(b), { open: false, powered: false });
  assert.deepEqual(w.sounds, []);
});

test("placed already powered, onPlace opens it silently", () => {
  const w = world();
  const b = w.put(handId, at, {}, 9);
  component.onPlace({ block: b });
  assert.deepEqual(state(b), { open: true, powered: true });
  assert.deepEqual(w.sounds, []);
});

test("an update for a trapdoor already gone (air in its place) changes nothing", () => {
  const w = world();
  const b = w.put(handId, at);
  b.typeId = "minecraft:air";
  b.permutation = _permutation("minecraft:air");
  b.setPermutation = () => { throw new Error("Failed to set property on block 'minecraft:air'"); };
  component.onRedstoneUpdate({ block: b, powerLevel: 0 });
  component.onPlace({ block: b });
  component.onPlayerInteract({ block: b });
  assert.deepEqual(w.sounds, []);
});
