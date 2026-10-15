// The namespace-free station kit's pure helpers (#245): src/portkit/runtime/station_core.js.
// The mod runtimes' own tests (cooking_pot, cutting_board, stove, skillet,
// feast, waystone, scrolls, warp_portal, warp_stone, memorial) exercise
// these through the bindings; this file pins each helper on its own.

import assert from "node:assert/strict";
import { test } from "node:test";

import * as kit from "../../src/portkit/runtime/station_core.js";

test("storage keys: component, dimension and position; the prefix lists one component", () => {
  const key = kit.storageKey("ns:portkit_thing", "minecraft:overworld", { x: 1, y: -64, z: 3 });
  assert.equal(key, "ns:portkit_thing|minecraft:overworld|1,-64,3");
  assert.ok(key.startsWith(kit.storagePrefix("ns:portkit_thing")));
  assert.ok(!kit.storageKey("ns:portkit_thing_order", "minecraft:overworld", { x: 0, y: 0, z: 0 })
    .startsWith(kit.storagePrefix("ns:portkit_thing")));
});

test("counter-clockwise step: Direction#getCounterClockWise; unknown facings count as north", () => {
  assert.deepEqual(kit.counterClockwiseStep("north"), [-1, 0]);
  assert.deepEqual(kit.counterClockwiseStep("west"), [0, 1]);
  assert.deepEqual(kit.counterClockwiseStep("south"), [1, 0]);
  assert.deepEqual(kit.counterClockwiseStep("east"), [0, -1]);
  assert.deepEqual(kit.counterClockwiseStep(undefined), [-1, 0]);
  assert.deepEqual(kit.counterClockwiseStep("up"), [-1, 0]);
});

test("heat rule: states that must match, states that must not, conductors over a source", () => {
  const block = (id, states = {}) => ({ id, state: (n) => states[n] });
  const lit = { id: "minecraft:campfire", not: { extinguished: true } };
  const lava = { id: "minecraft:cauldron", states: { cauldron_liquid: "lava" } };
  const heat = { sources: [lit, lava, { id: "minecraft:magma" }], conductors: [{ id: "minecraft:hopper" }],
    tray: [{ id: "minecraft:campfire" }] };
  assert.equal(kit.blockMatches(lit, undefined), false);
  assert.equal(kit.blockMatches(lit, block("minecraft:campfire", { extinguished: false })), true);
  assert.equal(kit.blockMatches(lit, block("minecraft:campfire", { extinguished: true })), false);
  assert.equal(kit.blockMatches(lava, block("minecraft:cauldron", { cauldron_liquid: "water" })), false);
  assert.equal(kit.isHeated(heat, block("minecraft:magma"), undefined), true);
  assert.equal(kit.isHeated(heat, block("minecraft:hopper"), block("minecraft:magma")), true);
  assert.equal(kit.isHeated(heat, block("minecraft:hopper"), block("minecraft:hopper")), false);
  assert.equal(kit.isHeated(heat, undefined, block("minecraft:magma")), false);
  assert.equal(kit.trayState(heat, block("minecraft:campfire", { extinguished: true })), "tray");
  assert.equal(kit.trayState(heat, undefined), "none");
});

test("destroy command: setblock air destroy at the position", () => {
  assert.equal(kit.destroyCommand({ x: 4, y: 70, z: -2 }), "setblock 4 70 -2 air destroy");
});

test("hold timer: finishes after the use time; slot switch, item change, a gone player or stop end it", () => {
  const player = (id, slot = 0) => ({ id, selectedSlotIndex: slot, isValid: true });
  const holding = new Map();
  const heldAt = (p, slot) => holding.get(`${p.id}:${slot}`);
  const timer = new kit.HoldTimer();
  const done = [];
  const a = player("a");
  holding.set("a:0", { typeId: "x:scroll" });
  timer.start(a, 0, "x:scroll", 3);
  assert.ok(timer.has("a"));
  timer.tick(heldAt, (c) => done.push(c.player.id));
  timer.tick(heldAt, (c) => done.push(c.player.id));
  assert.deepEqual(done, []);
  timer.tick(heldAt, (c) => done.push(c.player.id));
  assert.deepEqual(done, ["a"]);
  assert.ok(!timer.has("a"));

  const b = player("b");
  holding.set("b:0", { typeId: "x:scroll" });
  timer.start(b, 0, "x:scroll", 5);
  b.selectedSlotIndex = 1;
  timer.tick(heldAt, () => assert.fail("switched slot"));
  assert.ok(!timer.has("b"));

  const c = player("c");
  holding.set("c:0", { typeId: "x:other" });
  timer.start(c, 0, "x:scroll", 5);
  timer.tick(heldAt, () => assert.fail("different item"));
  assert.ok(!timer.has("c"));

  const d = player("d");
  holding.set("d:0", { typeId: "x:scroll" });
  timer.start(d, 0, "x:scroll", 5);
  d.isValid = false;
  timer.tick(heldAt, () => assert.fail("player gone"));
  assert.ok(!timer.has("d"));

  const e = player("e");
  holding.set("e:0", { typeId: "x:scroll" });
  timer.start(e, 0, "x:scroll", 1);
  timer.stop("e");
  timer.tick(heldAt, () => assert.fail("stopped"));
  assert.ok(!timer.has("e"));
});

test("hold timer: a zero or negative use time finishes on the first tick", () => {
  const timer = new kit.HoldTimer();
  const p = { id: "p", selectedSlotIndex: 2 };
  const done = [];
  timer.start(p, 2, "x:stone", 0);
  timer.tick(() => ({ typeId: "x:stone" }), (c) => done.push(c.typeId));
  assert.deepEqual(done, ["x:stone"]);
});
