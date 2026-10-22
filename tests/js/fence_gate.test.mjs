// The fixed fence gate runtime (src/portkit/runtime/fence_gate.js on fence_gate_core.js), offline
// under node. Run: node --import tests/js/register.mjs --test tests/js/fence_gate.test.mjs
// (tests/test_fence_gates.py runs it with PORTKIT_FENCE_GATE_TABLE set to a data table the
// converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import { registerFenceGates } from "../../src/portkit/runtime/fence_gate.js";
import { directionOf, inWall, pitch, placed, powerChange, sides, use } from "../../src/portkit/runtime/fence_gate_core.js";
import { _fire, _permutation, _startup, world as stubWorld } from "@minecraft/server";

const FALLBACK = {
  component: "examplemod:portkit_fence_gate",
  event: "portkit:fence_gate_use",
  states: { open: "examplemod:open", in_wall: "examplemod:in_wall", powered: "examplemod:powered" },
  pitch: [0.9, 1.0],
  walls: ["minecraft:cobblestone_wall", "examplemod:marble_wall"],
  gates: {
    "examplemod:oak_fence_gate": { open_sound: "open.fence_gate", close_sound: "close.fence_gate" },
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_FENCE_GATE_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerFenceGates(table);
const component = _startup()[table.component];
const S = table.states;
const gateId = Object.keys(table.gates)[0];
const wallId = table.walls[0];

// A tiny world: blocks by "x,y,z", each a Bedrock-like block reading its neighbours.
function makeWorld() {
  const blocks = new Map();
  const sounds = [];
  const dim = {
    id: "minecraft:overworld",
    playSound: (id, _loc, opts) => sounds.push({ id, pitch: opts?.pitch }),
    getBlock: (loc) => blocks.get(`${loc.x},${loc.y},${loc.z}`) ?? air(loc),
  };
  function air(loc) {
    return { typeId: "minecraft:air", location: loc, dimension: dim, permutation: _permutation("minecraft:air") };
  }
  function put(typeId, loc, states = {}, power = 0) {
    const b = {
      typeId, location: loc, dimension: dim, power,
      permutation: _permutation(typeId, typeId === gateId ? {
        "minecraft:cardinal_direction": "north", [S.open]: false, [S.powered]: false, [S.in_wall]: false, ...states,
      } : states),
      setPermutation(p) { this.permutation = p; },
      getRedstonePower() { return this.power; },
      center: () => ({ x: loc.x + 0.5, y: loc.y + 0.5, z: loc.z + 0.5 }),
    };
    blocks.set(`${loc.x},${loc.y},${loc.z}`, b);
    return b;
  }
  function remove(loc) {
    blocks.delete(`${loc.x},${loc.y},${loc.z}`);
    return air(loc);
  }
  return { put, remove, sounds, dim };
}

const at = { x: 0, y: 64, z: 0 };
const st = (b) => ({
  facing: b.permutation.getState("minecraft:cardinal_direction"),
  open: b.permutation.getState(S.open),
  powered: b.permutation.getState(S.powered),
  in_wall: b.permutation.getState(S.in_wall),
});

test("core: sides, in_wall, direction, placement, use, power, pitch (FenceGateBlock)", () => {
  assert.deepEqual(sides("north"), ["west", "east"]);
  assert.deepEqual(sides("south"), ["west", "east"]);
  assert.deepEqual(sides("east"), ["north", "south"]);
  assert.equal(inWall("north", (d) => d === "east"), true);
  assert.equal(inWall("north", (d) => d === "north"), false);
  assert.equal(inWall("west", (d) => d === "south"), true);
  assert.equal(directionOf({ x: 0, z: -1 }), "north");
  assert.equal(directionOf({ x: 0.9, z: 0.1 }), "east");
  assert.equal(directionOf({ x: -0.9, z: 0.3 }), "west");
  assert.equal(directionOf({ x: 0.1, z: 0.8 }), "south");
  assert.deepEqual(placed(true, false), { open: true, powered: true, in_wall: false });
  // A closed gate facing the player turns to face away, then opens.
  assert.deepEqual(use({ facing: "south", open: false }, "north"), { facing: "north", open: true, sound: "open" });
  // Facing away already, or sideways: keeps its facing.
  assert.deepEqual(use({ facing: "north", open: false }, "north"), { facing: "north", open: true, sound: "open" });
  assert.deepEqual(use({ facing: "east", open: false }, "north"), { facing: "east", open: true, sound: "open" });
  // An open gate closes, whatever way the player looks.
  assert.deepEqual(use({ facing: "east", open: true }, "west"), { facing: "east", open: false, sound: "close" });
  assert.equal(powerChange({ open: false, powered: false }, false), null);
  assert.deepEqual(powerChange({ open: false, powered: false }, true), { open: true, powered: true, sound: true });
  // Opened by hand, then powered: powered changes, open doesn't, no sound.
  assert.deepEqual(powerChange({ open: true, powered: false }, true), { open: true, powered: true, sound: false });
  assert.deepEqual(powerChange({ open: true, powered: true }, false), { open: false, powered: false, sound: true });
  assert.equal(pitch([0.9, 1.0], 0), 0.9);
  assert.ok(Math.abs(pitch([0.9, 1.0], 0.5) - 0.95) < 1e-9);
});

test("the component has the events a gate needs", () => {
  for (const name of ["onPlace", "onPlayerInteract", "onRedstoneUpdate"]) {
    assert.equal(typeof component[name], "function", name);
  }
});

test("a player's use opens it away from the player and closes it, with its sounds", () => {
  const w = makeWorld();
  const b = w.put(gateId, at, { "minecraft:cardinal_direction": "south" });
  // The player stands south of the gate looking north: the gate faces them, so it turns.
  component.onPlayerInteract({ block: b, player: { getViewDirection: () => ({ x: 0, y: 0, z: -1 }) } });
  assert.deepEqual(st(b), { facing: "north", open: true, powered: false, in_wall: false });
  component.onPlayerInteract({ block: b, player: { getViewDirection: () => ({ x: 0, y: 0, z: 1 }) } });
  assert.deepEqual(st(b), { facing: "north", open: false, powered: false, in_wall: false });
  assert.deepEqual(w.sounds.map((s) => s.id), [table.gates[gateId].open_sound, table.gates[gateId].close_sound]);
  assert.ok(w.sounds.every((s) => s.pitch >= 0.9 && s.pitch <= 1.0));
});

test("placed powered it opens; between walls it is lowered", () => {
  const w = makeWorld();
  w.put(wallId, { x: -1, y: 64, z: 0 });
  const b = w.put(gateId, at, { "minecraft:cardinal_direction": "north" }, 15);
  component.onPlace({ block: b });
  assert.deepEqual(st(b), { facing: "north", open: true, powered: true, in_wall: true });
  // A wall on the gate's front or back doesn't lower it.
  const c = w.put(gateId, { x: 5, y: 64, z: 0 }, { "minecraft:cardinal_direction": "east" });
  w.put(wallId, { x: 6, y: 64, z: 0 });
  component.onPlace({ block: c });
  assert.equal(st(c).in_wall, false);
});

test("redstone opens and closes it; a repeat changes nothing", () => {
  const w = makeWorld();
  const b = w.put(gateId, at);
  b.power = 15;
  component.onRedstoneUpdate({ block: b, powerLevel: 15 });
  assert.deepEqual(st(b), { facing: "north", open: true, powered: true, in_wall: false });
  component.onRedstoneUpdate({ block: b, powerLevel: 15 });
  b.power = 0;
  component.onRedstoneUpdate({ block: b, powerLevel: 0 });
  assert.deepEqual(st(b), { facing: "north", open: false, powered: false, in_wall: false });
  assert.equal(w.sounds.length, 2);
});

test("in_wall follows a player placing and breaking a wall beside it", () => {
  const w = makeWorld();
  const b = w.put(gateId, at, { "minecraft:cardinal_direction": "south" });
  const wall = w.put(wallId, { x: 1, y: 64, z: 0 });
  _fire("after", "playerPlaceBlock", { block: wall });
  assert.equal(st(b).in_wall, true);
  const gone = w.remove({ x: 1, y: 64, z: 0 });
  _fire("after", "playerBreakBlock", { block: gone });
  assert.equal(st(b).in_wall, false);
});

test("the use scriptevent uses the gate as a player facing that way", () => {
  const w = makeWorld();
  const b = w.put(gateId, at, { "minecraft:cardinal_direction": "west" });
  stubWorld._dimensions.set("overworld", w.dim);
  _fire("system", "scriptEventReceive", { id: table.event, message: "0 64 0 east" });
  assert.deepEqual(st(b), { facing: "east", open: true, powered: false, in_wall: false });
  _fire("system", "scriptEventReceive", { id: table.event, message: "0 64 0" });
  assert.equal(st(b).open, true);
});
