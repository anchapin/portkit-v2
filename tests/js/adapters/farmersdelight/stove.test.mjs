// The fixed stove runtime (src/portkit/adapters/farmersdelight/runtime), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/adapters/farmersdelight/stove.test.mjs
// (tests/adapters/farmersdelight/test_stove.py runs it with PORTKIT_STOVE_TABLE set to a data table
// the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../../../src/portkit/adapters/farmersdelight/runtime/stove_core.js";
import * as kit from "../../../../src/portkit/runtime/station_core.js";
import { registerStove } from "../../../../src/portkit/adapters/farmersdelight/runtime/stove.js";
import { GameMode, ItemStack, _dimension, _entity, _player, _startup, _stoveBlock, world } from "@minecraft/server";

const FALLBACK = {
  block: "farmersdelight:stove",
  burn: { amount: 1.0, cause: "campfire" },
  component: "farmersdelight:portkit_stove",
  extinguish: {
    shovel: { items: ["minecraft:iron_shovel", "minecraft:wooden_shovel"], tags: ["minecraft:is_shovel"] },
    water: { "minecraft:water_bucket": "minecraft:bucket" },
  },
  ignite: { fire_charge: ["minecraft:fire_charge"], flint_and_steel: ["minecraft:flint_and_steel"] },
  lit_state: "farmersdelight:lit",
  recipes: [
    { id: "minecraft:cooked_beef_from_campfire_cooking", ingredient: ["minecraft:beef"],
      result: { item: "minecraft:cooked_beef", count: 1 }, cookingtime: 600 },
    { id: "farmersdelight:fried_egg_from_campfire_cooking", ingredient: ["minecraft:egg"],
      result: { item: "farmersdelight:fried_egg", count: 1 }, cookingtime: 600 },
  ],
  slots: 6,
  sounds: {
    break: { id: "random.break", pitch: 1.0, volume: 1.0 },
    crackle: { chance_per_tick: 0.1, id: "block.campfire.crackle", pitch: 1.0, volume: 1.0 },
    fire_charge: { id: "item.firecharge.use", pitch: 1.0, pitch_spread: 0.2, volume: 1.0 },
    flint_and_steel: { id: "fire.ignite", pitch: 1.0, pitch_max: 1.2, pitch_min: 0.8, volume: 1.0 },
    place: { id: "block.lantern.place", pitch: 1.0, volume: 0.5 },
    shovel: { id: "random.fizz", pitch: 1.0, volume: 1.0 },
    water: { id: "random.fizz", pitch: 1.0, volume: 1.0 },
  },
  tick_interval: 10,
};

const generated = process.env.PORTKIT_STOVE_TABLE
  ? (await import(pathToFileURL(process.env.PORTKIT_STOVE_TABLE).href)).default
  : null;
const table = generated ?? FALLBACK;
registerStove(table);
const component = _startup()[table.component];
const beef = table.recipes.find((r) => r.ingredient.includes("minecraft:beef"));

function withRandom(value, fn) {
  const original = Math.random;
  Math.random = () => value;
  try { return fn(); } finally { Math.random = original; }
}

function stored(block) {
  const raw = world.getDynamicProperty(kit.storageKey(table.component, block.dimension.id, block.location));
  return raw === undefined ? undefined : JSON.parse(raw);
}

function use(block, player) {
  component.onPlayerInteract({ block, dimension: block.dimension, player });
}

function tickTimes(block, n) {
  for (let i = 0; i < n; i++) component.onTick({ block, dimension: block.dimension });
}

let x = 0;
function freshBlock(opts = {}) {
  x += 3; // a new position per test, so dynamic properties don't leak between tests
  return _stoveBlock(_dimension(), { location: { x, y: 64, z: 5 }, ...opts });
}

// -- pure logic ---------------------------------------------------------------

test("interaction follows useItemOn: lit puts out, unlit lights, food goes on", () => {
  const no = () => false;
  assert.equal(core.interaction(FALLBACK, true, "minecraft:iron_shovel", no), "extinguish_shovel");
  assert.equal(core.interaction(FALLBACK, true, "mod:any_shovel", (t) => t === "minecraft:is_shovel"), "extinguish_shovel");
  assert.equal(core.interaction(FALLBACK, true, "minecraft:water_bucket", no), "extinguish_water");
  assert.equal(core.interaction(FALLBACK, false, "minecraft:flint_and_steel", no), "ignite_flint");
  assert.equal(core.interaction(FALLBACK, false, "minecraft:fire_charge", no), "ignite_charge");
  // lit + flint and steel: nothing to ignite, and no campfire recipe takes it.
  assert.equal(core.interaction(FALLBACK, true, "minecraft:flint_and_steel", no), null);
  // unlit + shovel: nothing to put out.
  assert.equal(core.interaction(FALLBACK, false, "minecraft:iron_shovel", no), null);
  assert.equal(core.interaction(FALLBACK, false, "minecraft:beef", no), "place");
  assert.equal(core.interaction(FALLBACK, true, "minecraft:beef", no), "place");
  assert.equal(core.interaction(FALLBACK, true, undefined, no), null);
});

test("placeFood takes one item onto the first free spot; full is full", () => {
  const stove = core.emptyStove();
  for (let i = 0; i < 6; i++) assert.equal(core.placeFood(stove, { id: "minecraft:beef", amount: 5 }, FALLBACK.recipes[0]), i);
  assert.equal(stove.items[0].amount, 1);
  assert.equal(stove.total[3], 600);
  assert.equal(core.placeFood(stove, { id: "minecraft:beef", amount: 1 }, FALLBACK.recipes[0]), -1);
});

test("lit cooks for exactly the cooking time; unlit cools by 2 a tick", () => {
  const stove = core.emptyStove();
  core.placeFood(stove, { id: "minecraft:beef", amount: 1 }, FALLBACK.recipes[0]);
  let done;
  for (let run = 1; run <= 59; run++) {
    done = core.step(stove, { lit: true, interval: 10, recipes: FALLBACK.recipes });
    assert.deepEqual(done.cooked, []);
  }
  assert.equal(stove.progress[0], 590);
  // Off the heat for 10 runs: 590 - 2*10*10 = 390.
  for (let run = 0; run < 10; run++) core.step(stove, { lit: false, interval: 10, recipes: FALLBACK.recipes });
  assert.equal(stove.progress[0], 390);
  for (let run = 0; run < 21; run++) done = core.step(stove, { lit: true, interval: 10, recipes: FALLBACK.recipes });
  assert.deepEqual(done.cooked, [{ id: "minecraft:cooked_beef", amount: 1 }]);
  assert.equal(core.isEmpty(stove), true);
});

test("an item without a recipe pops out as itself (orElse(ingredient))", () => {
  const stove = core.emptyStove();
  stove.items[2] = { id: "minecraft:stick", amount: 1, nameTag: "x" };
  stove.total[2] = 10;
  const done = core.step(stove, { lit: true, interval: 10, recipes: FALLBACK.recipes });
  assert.deepEqual(done.cooked, [{ id: "minecraft:stick", amount: 1, nameTag: "x" }]);
});

test("burns: lit, living, not sneaking, on the ground over the stove", () => {
  const at = { x: 0, y: 64, z: 0 };
  const on = (over = {}) => ({ living: true, sneaking: false, onGround: true, feet: { x: 0.5, y: 65, z: 0.5 }, ...over });
  assert.equal(core.burns(true, on(), at), true);
  assert.equal(core.burns(false, on(), at), false);
  assert.equal(core.burns(true, on({ sneaking: true }), at), false);
  assert.equal(core.burns(true, on({ living: false }), at), false);
  assert.equal(core.burns(true, on({ onGround: false }), at), false);
  assert.equal(core.burns(true, on({ feet: { x: 1.2, y: 65, z: 0.5 } }), at), false); // next block over
  assert.equal(core.burns(true, on({ feet: { x: 0.5, y: 65.5, z: 0.5 } }), at), false); // on something taller
});

test("sound chance and Unbreaking", () => {
  assert.ok(Math.abs(core.soundChance(0.1, 10) - (1 - 0.9 ** 10)) < 1e-12);
  assert.equal(core.takesDamage(0, () => 0), true);
  assert.equal(core.takesDamage(3, () => 0.5), false);
  assert.equal(core.takesDamage(3, () => 0.8), true);
});

// -- Bedrock binding (stub) -----------------------------------------------------

test("placing a lit stove sets lit", () => {
  const block = freshBlock({ lit: "false" });
  const event = { block, face: "Up", permutationToPlace: block.permutation };
  component.beforeOnPlayerPlace(event);
  assert.equal(event.permutationToPlace.getState("farmersdelight:lit"), "true");
});

test("food goes on one at a time, cooks while lit and pops out on top", () => {
  const block = freshBlock();
  const player = _player(block.dimension, new ItemStack("minecraft:beef", 3));
  use(block, player);
  assert.equal(player.held.amount, 2);
  assert.equal(stored(block).items[0].id, "minecraft:beef");
  assert.equal(block.dimension.sounds.at(-1).id, "block.lantern.place");
  assert.match(player.actionbar.at(-1), /stove lit \| cooking: minecraft:beef 0% \| 5 free/);
  withRandom(0.99, () => tickTimes(block, beef.cookingtime / table.tick_interval));
  const popped = block.dimension.spawned.at(-1);
  assert.equal(popped.stack.typeId, beef.result.item);
  assert.deepEqual(popped.location, { x: block.location.x + 0.5, y: 65, z: 5.5 });
  assert.equal(popped.impulses[0].y, 0.1);
  assert.equal(stored(block), undefined);
});

test("creative keeps the held stack", () => {
  const block = freshBlock();
  const player = _player(block.dimension, new ItemStack("minecraft:beef", 1), { creative: true });
  use(block, player);
  assert.equal(player.held.amount, 1);
  assert.equal(stored(block).items.filter(Boolean).length, 1);
});

test("a covered top refuses food and drops what is on it", () => {
  const block = freshBlock();
  const player = _player(block.dimension, new ItemStack("minecraft:beef", 2));
  use(block, player);
  block.setAbove({ isAir: false, isLiquid: false });
  use(block, player);
  assert.equal(player.held.amount, 1); // refused
  withRandom(0.99, () => tickTimes(block, 1));
  assert.equal(block.dimension.spawned.at(-1).stack.typeId, "minecraft:beef");
  assert.equal(stored(block), undefined);
  // Water above has no shape in Java: not covered.
  block.setAbove({ isAir: false, isLiquid: true });
  use(block, player);
  assert.equal(player.held, undefined);
});

test("a shovel puts it out and takes durability; flint and steel lights it", () => {
  const block = freshBlock();
  const shovel = new ItemStack("minecraft:iron_shovel", 1);
  const player = _player(block.dimension, shovel);
  withRandom(0.5, () => use(block, player));
  assert.equal(block.permutation.getState("farmersdelight:lit"), "false");
  assert.equal(shovel.getComponent("minecraft:durability").damage, 1);
  assert.equal(block.dimension.sounds.at(-1).id, "random.fizz");
  const flint = _player(block.dimension, new ItemStack("minecraft:flint_and_steel", 1));
  withRandom(0.5, () => use(block, flint));
  assert.equal(block.permutation.getState("farmersdelight:lit"), "true");
  const sound = block.dimension.sounds.at(-1);
  assert.equal(sound.id, "fire.ignite");
  assert.ok(Math.abs(sound.pitch - 1.0) < 1e-9);
});

test("a water bucket puts it out and leaves its remainder; a fire charge is used up", () => {
  const block = freshBlock();
  const player = _player(block.dimension, new ItemStack("minecraft:water_bucket", 1));
  use(block, player);
  assert.equal(block.permutation.getState("farmersdelight:lit"), "false");
  assert.equal(player.held.typeId, "minecraft:bucket");
  const charge = _player(block.dimension, new ItemStack("minecraft:fire_charge", 2));
  use(block, charge);
  assert.equal(block.permutation.getState("farmersdelight:lit"), "true");
  assert.equal(charge.held.amount, 1);
  assert.equal(block.dimension.sounds.at(-1).id, "item.firecharge.use");
});

test("unlit, food cools instead of cooking", () => {
  const block = freshBlock();
  use(block, _player(block.dimension, new ItemStack("minecraft:beef", 1)));
  withRandom(0.99, () => tickTimes(block, 10));
  assert.equal(stored(block).progress[0], 100);
  block.setPermutation(block.permutation.withState("farmersdelight:lit", "false"));
  withRandom(0.99, () => tickTimes(block, 3));
  assert.equal(stored(block).progress[0], 40);
});

test("a lit stove burns who stands on it, not sneakers or items", () => {
  const block = freshBlock();
  const top = { x: block.location.x + 0.5, y: 65, z: 5.5 };
  const zombie = _entity(top);
  const sneaker = _entity(top, { typeId: "minecraft:player", sneaking: true });
  const item = _entity(top, { typeId: "minecraft:item", living: false });
  const boat = _entity(top, { typeId: "minecraft:boat", living: false, inanimate: true });
  block.dimension.entities.push(zombie, sneaker, item, boat);
  withRandom(0.99, () => tickTimes(block, 2));
  assert.deepEqual(zombie.damage, [{ amount: 1, cause: "campfire" }, { amount: 1, cause: "campfire" }]);
  assert.deepEqual(sneaker.damage, []);
  assert.deepEqual(item.damage, []);
  assert.deepEqual(boat.damage, []);
  block.setPermutation(block.permutation.withState("farmersdelight:lit", "false"));
  withRandom(0.99, () => tickTimes(block, 1));
  assert.equal(zombie.damage.length, 2);
});

test("crackles only while lit", () => {
  const block = freshBlock();
  withRandom(0.0, () => tickTimes(block, 1));
  assert.equal(block.dimension.sounds.at(-1).id, "block.campfire.crackle");
  const quiet = freshBlock({ lit: "false" });
  withRandom(0.0, () => tickTimes(quiet, 1));
  assert.equal(quiet.dimension.sounds.length, 0);
});

test("breaking drops the food; a fresh stove doesn't inherit it; relighting keeps it", () => {
  const block = freshBlock();
  use(block, _player(block.dimension, new ItemStack("minecraft:beef", 2)));
  component.onPlace({ block, previousBlock: { type: { id: table.block } } });
  assert.ok(stored(block));
  component.onPlayerBreak({ block, dimension: block.dimension, player: undefined });
  assert.equal(block.dimension.spawned.at(-1).stack.typeId, "minecraft:beef");
  assert.equal(stored(block), undefined);
  use(block, _player(block.dimension, new ItemStack("minecraft:beef", 1)));
  component.onPlace({ block, previousBlock: { type: { id: "minecraft:air" } } });
  assert.equal(stored(block), undefined);
});

test("the generated table, when given, has the shape the runtime reads", () => {
  if (!generated) return;
  for (const key of ["block", "component", "lit_state", "recipes", "extinguish", "ignite", "sounds", "burn"]) {
    assert.ok(key in generated, key);
  }
  assert.equal(generated.tick_interval, 10);
  assert.equal(generated.slots, 6);
  for (const r of generated.recipes) assert.equal(r.cookingtime % generated.tick_interval, 0, r.id);
});
