// The fixed cooking-pot runtime (src/portkit/runtime), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/cooking_pot.test.mjs
// (tests/test_cooking_pot.py runs it with PORTKIT_COOKING_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../src/portkit/runtime/cooking_pot_core.js";
import * as kit from "../../src/portkit/runtime/station_core.js";
import { registerCookingPot } from "../../src/portkit/runtime/cooking_pot.js";
import { Direction, ItemStack, _dimension, _player, _potBlock, _startup, world } from "@minecraft/server";

const FALLBACK = {
  block: "farmersdelight:cooking_pot",
  component: "farmersdelight:portkit_cooking_pot",
  heat: {
    conductors: [{ id: "minecraft:hopper" }],
    sources: [
      { id: "minecraft:magma" },
      { id: "minecraft:cauldron", not: { fill_level: 0 }, states: { cauldron_liquid: "lava" } },
      { id: "minecraft:campfire", states: { extinguished: false } },
      { id: "minecraft:fire" },
    ],
    tray: [{ id: "minecraft:campfire" }, { id: "minecraft:fire" }],
  },
  max_slot_meal: 64,
  recipes: [
    { id: "farmersdelight:cooking/beef_stew", ingredients: [["minecraft:beef"], ["minecraft:carrot"], ["minecraft:potato", "minecraft:baked_potato"]],
      result: { item: "farmersdelight:beef_stew", count: 1 }, container: "minecraft:bowl", cookingtime: 200, experience: 1.0 },
    { id: "farmersdelight:cooking/hot_cocoa", ingredients: [["minecraft:milk_bucket", "farmersdelight:milk_bottle"], ["minecraft:sugar"], ["minecraft:cocoa_beans"], ["minecraft:cocoa_beans"]],
      result: { item: "farmersdelight:hot_cocoa", count: 1 }, container: "minecraft:glass_bottle", cookingtime: 200, experience: 1.0 },
    { id: "farmersdelight:cooking/dumplings", ingredients: [["farmersdelight:wheat_dough"], ["farmersdelight:cabbage"]],
      result: { item: "farmersdelight:dumplings", count: 2 }, container: null, cookingtime: 200, experience: 0.35 },
  ],
  remainders: { "minecraft:milk_bucket": "minecraft:bucket" },
  serving_containers: ["minecraft:bowl", "minecraft:bucket", "minecraft:glass_bottle"],
  sounds: {
    boil: { chance_per_tick: 0.1, id: "farmersdelight:block.cooking_pot.boil", pitch_max: 1.1, pitch_min: 0.9, volume: 0.5 },
    boil_soup: { chance_per_tick: 0.1, id: "farmersdelight:block.cooking_pot.boil_soup", pitch_max: 1.1, pitch_min: 0.9, volume: 0.5 },
    handle: { id: "block.lantern.place", pitch: 1.0, volume: 0.7 },
    serve: { id: "armor.equip_generic", pitch: 1.0, volume: 1.0 },
  },
  support_state: "farmersdelight:support",
  tick_interval: 10,
};

const table = process.env.PORTKIT_COOKING_TABLE
  ? (await import(pathToFileURL(process.env.PORTKIT_COOKING_TABLE).href)).default
  : FALLBACK;
registerCookingPot(table);
const component = _startup()[table.component];
const max = () => 64;
const ctx = (heated, extra = {}) => ({ heated, recipes: FALLBACK.recipes, interval: 10, maxAmount: max,
  remainders: FALLBACK.remainders, ...extra });
const s = (id, amount = 1) => ({ id, amount });
const MAGMA = [{ id: "minecraft:magma" }];

function withRandom(value, fn) {
  const original = Math.random;
  Math.random = () => value;
  try { return fn(); } finally { Math.random = original; }
}

function potWith(...ids) {
  const pot = core.emptyPot();
  ids.forEach((id, i) => { pot.slots[i] = typeof id === "string" ? s(id, 1) : id; });
  return pot;
}

// -- pure logic ---------------------------------------------------------------

test("a recipe matches when every ingredient takes its own filled slot", () => {
  const stew = FALLBACK.recipes[0];
  assert.equal(core.matches(stew, ["minecraft:potato", "minecraft:beef", "minecraft:carrot"]), true);
  assert.equal(core.matches(stew, ["minecraft:beef", "minecraft:carrot"]), false); // count differs
  assert.equal(core.matches(stew, ["minecraft:beef", "minecraft:carrot", "minecraft:carrot"]), false);
  const cocoa = FALLBACK.recipes[1];
  // two cocoa slots for two cocoa ingredients; one slot of 2 cocoa is not two.
  assert.equal(core.matches(cocoa, ["minecraft:cocoa_beans", "minecraft:sugar", "minecraft:cocoa_beans", "farmersdelight:milk_bottle"]), true);
  assert.equal(core.findRecipe(FALLBACK.recipes, potWith(s("minecraft:cocoa_beans", 2), "minecraft:sugar", "minecraft:milk_bucket")), undefined);
});

test("the meal slot stacks to max(64, stack size) of the same meal", () => {
  const r = FALLBACK.recipes[0];
  assert.equal(core.canCook(r, null, 16), true);
  assert.equal(core.canCook(r, s("farmersdelight:beef_stew", 63), 16), true);
  assert.equal(core.canCook(r, s("farmersdelight:beef_stew", 64), 16), false);
  assert.equal(core.canCook(r, s("farmersdelight:fish_stew", 1), 16), false);
});

test("a heated pot cooks after cookingtime ticks, one item from each slot", () => {
  const pot = potWith(s("minecraft:beef", 2), "minecraft:carrot", "minecraft:potato");
  for (let i = 0; i < 19; i++) assert.equal(core.step(pot, ctx(true)).cooked, null);
  assert.equal(pot.cookTime, 190);
  const done = core.step(pot, ctx(true));
  assert.equal(done.cooked.id, "farmersdelight:cooking/beef_stew");
  assert.deepEqual(pot.meal, { id: "farmersdelight:beef_stew", amount: 1 });
  assert.equal(pot.mealContainer, "minecraft:bowl");
  assert.equal(pot.cookTime, 0);
  assert.deepEqual(pot.slots[0], s("minecraft:beef", 1));
  assert.equal(pot.slots[1], null);
  assert.deepEqual(pot.used, { "farmersdelight:cooking/beef_stew": 1 });
});

test("the timer falls by 2 a tick off the heat, and nothing cooks", () => {
  const pot = potWith("minecraft:beef", "minecraft:carrot", "minecraft:potato");
  for (let i = 0; i < 5; i++) core.step(pot, ctx(true));
  assert.equal(pot.cookTime, 50);
  core.step(pot, ctx(false));
  assert.equal(pot.cookTime, 30);
  core.step(pot, ctx(false));
  core.step(pot, ctx(false));
  assert.equal(pot.cookTime, 0);
  assert.equal(pot.meal, null);
});

test("used-up ingredients eject their remainders", () => {
  const pot = potWith("minecraft:milk_bucket", "minecraft:sugar", "minecraft:cocoa_beans", "minecraft:cocoa_beans");
  let done;
  for (let i = 0; i < 20; i++) done = core.step(pot, ctx(true));
  assert.deepEqual(done.ejected, ["minecraft:bucket"]);
  assert.deepEqual(core.ejectOffset("north"), { dx: -0.25, dy: 0.7, dz: 0, vx: -0.08, vy: 0.25, vz: 0 });
});

test("a meal with no container goes to the output; one with a container waits for it", () => {
  const pot = potWith("farmersdelight:wheat_dough", "farmersdelight:cabbage");
  for (let i = 0; i < 20; i++) core.step(pot, ctx(true));
  assert.equal(pot.meal, null);
  assert.deepEqual(pot.output, { id: "farmersdelight:dumplings", amount: 2 });

  const stew = core.emptyPot();
  stew.meal = s("farmersdelight:beef_stew", 3);
  stew.mealContainer = "minecraft:bowl";
  core.step(stew, ctx(false));
  assert.equal(stew.output, null);
  stew.container = s("minecraft:bowl", 2);
  core.step(stew, ctx(false));
  assert.deepEqual(stew.output, { id: "farmersdelight:beef_stew", amount: 2 });
  assert.deepEqual(stew.meal, s("farmersdelight:beef_stew", 1));
  assert.equal(stew.container, null);
});

test("serving takes one portion for the meal's container only", () => {
  const pot = core.emptyPot();
  pot.meal = s("farmersdelight:beef_stew", 2);
  pot.mealContainer = "minecraft:bowl";
  assert.equal(core.serve(pot, "minecraft:glass_bottle"), undefined);
  assert.equal(core.serve(pot, "minecraft:bowl"), "farmersdelight:beef_stew");
  assert.equal(pot.meal.amount, 1);
  assert.equal(core.serve(pot, "minecraft:bowl"), "farmersdelight:beef_stew");
  assert.equal(pot.meal, null);
  assert.equal(core.serve(pot, "minecraft:bowl"), undefined);
});

test("containers go to their slot; ingredients to the first empty slot, then onto the same item", () => {
  const pot = core.emptyPot();
  assert.equal(core.insert(pot, s("minecraft:bowl", 10), 64, FALLBACK.serving_containers), 10);
  assert.equal(core.insert(pot, s("minecraft:bowl", 60), 64, FALLBACK.serving_containers), 54);
  assert.deepEqual(pot.container, s("minecraft:bowl", 64));
  // Two uses with apples make two apple slots (apple cider needs both).
  assert.equal(core.insert(pot, s("minecraft:apple", 40), 64, []), 40);
  assert.equal(core.insert(pot, s("minecraft:apple", 40), 64, []), 40);
  assert.deepEqual(pot.slots[0], s("minecraft:apple", 40));
  assert.deepEqual(pot.slots[1], s("minecraft:apple", 40));
  for (let i = 0; i < 4; i++) core.insert(pot, s(`x:i${i}`, 1), 1, []);
  // No slot empty: onto the same item, up to its stack size.
  assert.equal(core.insert(pot, s("minecraft:apple", 64), 64, []), 48);
  assert.equal(core.insert(pot, s("x:full", 1), 1, []), 0); // all six slots taken
});

test("an empty hand takes the output, then the last ingredient, then containers", () => {
  const pot = potWith("minecraft:beef", "minecraft:carrot");
  pot.container = s("minecraft:bowl", 3);
  pot.output = s("farmersdelight:dumplings", 2);
  assert.equal(core.takeOut(pot).from, "output");
  assert.deepEqual(core.takeOut(pot), { from: "ingredient", stack: s("minecraft:carrot", 1) });
  assert.equal(core.takeOut(pot).stack.id, "minecraft:beef");
  assert.equal(core.takeOut(pot).from, "container");
  assert.equal(core.takeOut(pot), undefined);
});

test("experience is floor(count x xp) plus the fraction by chance", () => {
  const used = { "farmersdelight:cooking/dumplings": 3 }; // 1.05
  assert.equal(core.experience(used, FALLBACK.recipes, () => 0.04), 2);
  assert.equal(core.experience(used, FALLBACK.recipes, () => 0.06), 1);
});

test("heat: lit sources, conductors over a source, and the tray rule", () => {
  const block = (id, states = {}) => ({ id, state: (n) => states[n] });
  const heat = FALLBACK.heat;
  assert.equal(kit.isHeated(heat, block("minecraft:magma"), undefined), true);
  assert.equal(kit.isHeated(heat, block("minecraft:campfire", { extinguished: true }), undefined), false);
  assert.equal(kit.isHeated(heat, block("minecraft:campfire", { extinguished: false }), undefined), true);
  assert.equal(kit.isHeated(heat, block("minecraft:cauldron", { cauldron_liquid: "lava", fill_level: 0 }), undefined), false);
  assert.equal(kit.isHeated(heat, block("minecraft:cauldron", { cauldron_liquid: "lava", fill_level: 6 }), undefined), true);
  assert.equal(kit.isHeated(heat, block("minecraft:hopper"), block("minecraft:magma")), true);
  assert.equal(kit.isHeated(heat, block("minecraft:hopper"), block("minecraft:stone")), false);
  // Tray only asks whether the block is one; an unlit campfire still holds the tray.
  assert.equal(kit.trayState(heat, block("minecraft:campfire", { extinguished: true })), "tray");
  assert.equal(kit.trayState(heat, block("minecraft:magma")), "none");
  assert.ok(Math.abs(core.boilChance(0.1, 10) - (1 - 0.9 ** 10)) < 1e-12);
});

// -- the Bedrock binding, against the stub ------------------------------------

function fresh(below = MAGMA) {
  world._properties.clear();
  const dimension = _dimension();
  return { dimension, block: _potBlock(dimension, { below }) };
}

const use = (block, dimension, player) => component.onPlayerInteract({ block, dimension, player });
const tick = (block, dimension, n = 1) => { for (let i = 0; i < n; i++) component.onTick({ block, dimension }); };

test("the component registers under the table's id with a tick", () => {
  assert.equal(typeof component.onPlayerInteract, "function");
  assert.equal(typeof component.onTick, "function");
  assert.equal(typeof component.beforeOnPlayerPlace, "function");
});

test("fill, cook on heat, serve into bowls", { skip: !!process.env.PORTKIT_COOKING_TABLE }, () => {
  const { dimension, block } = fresh();
  for (const id of ["minecraft:beef", "minecraft:carrot", "minecraft:potato"]) {
    const player = _player(dimension, new ItemStack(id, 1));
    use(block, dimension, player);
    assert.equal(player.held, undefined);
  }
  withRandom(0.99, () => tick(block, dimension, 20));
  const bowls = new ItemStack("minecraft:bowl", 4);
  const player = _player(dimension, bowls);
  use(block, dimension, player);
  assert.equal(player.held.amount, 3);
  assert.equal(player.inventory[0].typeId, "farmersdelight:beef_stew");
  assert.equal(dimension.sounds.at(-1).id, "armor.equip_generic");
  // Nothing left: storage is cleared once the experience is paid... it isn't yet.
  assert.ok(world._properties.size === 1);
});

test("an unheated pot does not cook", { skip: !!process.env.PORTKIT_COOKING_TABLE }, () => {
  const { dimension, block } = fresh([]);
  for (const id of ["minecraft:beef", "minecraft:carrot", "minecraft:potato"]) use(block, dimension, _player(dimension, new ItemStack(id, 1)));
  tick(block, dimension, 40);
  const player = _player(dimension, new ItemStack("minecraft:bowl", 1));
  use(block, dimension, player); // no meal: the bowl goes to the container slot
  assert.equal(player.held, undefined);
  assert.match(player.actionbar.at(-1), /not heated/);
});

test("output taken by hand pays the experience", { skip: !!process.env.PORTKIT_COOKING_TABLE }, () => {
  const { dimension, block } = fresh();
  for (const id of ["farmersdelight:wheat_dough", "farmersdelight:cabbage"]) use(block, dimension, _player(dimension, new ItemStack(id, 1)));
  withRandom(0.99, () => tick(block, dimension, 20));
  const player = _player(dimension, undefined);
  withRandom(0.0, () => use(block, dimension, player));
  assert.equal(player.inventory[0].typeId, "farmersdelight:dumplings");
  assert.equal(player.inventory[0].amount, 2);
  assert.equal(player.experience, 1); // 0.35 floors to 0, +1 by chance
  assert.equal(world._properties.size, 0);
});

test("ingredient remainders eject toward the facing turned counter-clockwise", { skip: !!process.env.PORTKIT_COOKING_TABLE }, () => {
  const { dimension, block } = fresh();
  for (const id of ["minecraft:milk_bucket", "minecraft:sugar", "minecraft:cocoa_beans", "minecraft:cocoa_beans"]) {
    use(block, dimension, _player(dimension, new ItemStack(id, 1)));
  }
  withRandom(0.99, () => tick(block, dimension, 20));
  const bucket = dimension.spawned.find((e) => e.stack.typeId === "minecraft:bucket");
  assert.ok(bucket);
  assert.deepEqual(bucket.location, { x: 4.25, y: 70.7, z: 8.5 });
  assert.deepEqual(bucket.impulses[0], { x: -0.08, y: 0.25, z: 0 });
});

test("sneaking with an empty hand toggles the handle", () => {
  const { dimension, block } = fresh();
  const player = _player(dimension, undefined);
  player.isSneaking = true;
  use(block, dimension, player);
  assert.equal(block.permutation.getState("farmersdelight:support"), "handle");
  use(block, dimension, player);
  assert.equal(block.permutation.getState("farmersdelight:support"), "none");
  assert.equal(dimension.sounds.at(-1).volume, 0.7);
});

test("placement: against a ceiling hangs on the handle, over a fire sits on a tray", () => {
  const dimension = _dimension();
  const event = (face, below) => {
    const block = _potBlock(dimension, { below });
    return { block, face, dimension, permutationToPlace: block.permutation };
  };
  const ceiling = event(Direction.Down, []);
  component.beforeOnPlayerPlace(ceiling);
  assert.equal(ceiling.permutationToPlace.getState("farmersdelight:support"), "handle");
  const fire = event(Direction.Up, [{ id: "minecraft:fire" }]);
  component.beforeOnPlayerPlace(fire);
  assert.equal(fire.permutationToPlace.getState("farmersdelight:support"), table.heat.tray.some((r) => r.id === "minecraft:fire") ? "tray" : "none");
});

test("the tray follows the block below; the handle stays", () => {
  const { dimension, block } = fresh([{ id: "minecraft:campfire", states: { extinguished: false } }]);
  tick(block, dimension);
  assert.equal(block.permutation.getState("farmersdelight:support"), table.heat.tray.length ? "tray" : "none");
  block.setPermutation(block.permutation.withState("farmersdelight:support", "handle"));
  tick(block, dimension);
  assert.equal(block.permutation.getState("farmersdelight:support"), "handle");
});

test("breaking drops everything, the meal as items", { skip: !!process.env.PORTKIT_COOKING_TABLE }, () => {
  const { dimension, block } = fresh();
  use(block, dimension, _player(dimension, new ItemStack("minecraft:carrot", 5)));
  use(block, dimension, _player(dimension, new ItemStack("minecraft:bowl", 2)));
  const pot = JSON.parse([...world._properties.values()][0]);
  pot.meal = { id: "farmersdelight:beef_stew", amount: 3 };
  pot.mealContainer = "minecraft:bowl";
  world._properties.set([...world._properties.keys()][0], JSON.stringify(pot));
  component.onPlayerBreak({ block, dimension, player: _player(dimension, undefined) });
  const dropped = Object.fromEntries(dimension.spawned.map((e) => [e.stack.typeId, e.stack.amount]));
  assert.deepEqual(dropped, { "minecraft:carrot": 5, "minecraft:bowl": 2, "farmersdelight:beef_stew": 3 });
  assert.equal(world._properties.size, 0);
});

test("a state change keeps the contents; a fresh pot starts empty", () => {
  const { dimension, block } = fresh();
  use(block, dimension, _player(dimension, new ItemStack("minecraft:carrot", 1)));
  component.onPlace({ block, dimension, previousBlock: block.permutation });
  assert.equal(world._properties.size, 1);
  component.onPlace({ block, dimension, previousBlock: { type: { id: "minecraft:air" } } });
  assert.equal(world._properties.size, 0);
});
