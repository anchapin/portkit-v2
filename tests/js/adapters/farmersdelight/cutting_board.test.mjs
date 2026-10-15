// The fixed cutting-board runtime (src/portkit/adapters/farmersdelight/runtime), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/adapters/farmersdelight/cutting_board.test.mjs
// (tests/adapters/farmersdelight/test_stations.py runs it with PORTKIT_CUTTING_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../../../src/portkit/adapters/farmersdelight/runtime/cutting_board_core.js";
import * as kit from "../../../../src/portkit/runtime/station_core.js";
import { registerCuttingBoard } from "../../../../src/portkit/adapters/farmersdelight/runtime/cutting_board.js";
import { ItemStack, _block, _dimension, _player, _startup, world } from "@minecraft/server";

const SHOVELS = ["minecraft:iron_shovel", "minecraft:wooden_shovel"];
const KNIVES = ["farmersdelight:flint_knife", "farmersdelight:iron_knife"];
const FALLBACK = {
  block: "farmersdelight:cutting_board",
  component: "farmersdelight:portkit_cutting_board",
  fortune_bonus: 0.1,
  messages: {
    no_recipe: "tile.farmersdelight:cutting_board.invalid_tool.name",
    remaining: "tile.farmersdelight:cutting_board.remaining_items.name",
  },
  recipes: [
    { id: "farmersdelight:cutting/cabbage", ingredient: ["farmersdelight:cabbage"],
      results: [{ chance: 1.0, count: 2, item: "farmersdelight:cabbage_leaf" }],
      tool: { items: KNIVES, tags: [] } },
    { id: "farmersdelight:cutting/gravel", ingredient: ["minecraft:gravel"],
      results: [{ chance: 1.0, count: 1, item: "minecraft:gravel" }, { chance: 0.1, count: 1, item: "minecraft:flint" }],
      tool: { items: SHOVELS, tags: ["minecraft:is_shovel"] } },
  ],
  sound_tools: { knife: KNIVES, shears: ["minecraft:shears"] },
  sounds: {
    break: { id: "random.break", pitch: 1.0, volume: 1.0 },
    knife: { id: "farmersdelight:block.cutting_board.knife_cut", pitch: 1.0, volume: 0.8 },
    other: { id: "dig.wood", pitch: 0.8, volume: 1.0 },
    place: { id: "place.wood", pitch: 0.8, volume: 1.0 },
    recipe: { pitch: 1.0, volume: 1.0 },
    remove: { id: "hit.wood", pitch: 0.5, volume: 0.25 },
    shears: { id: "mob.sheep.shear", pitch: 1.0, volume: 1.0 },
  },
};

const table = process.env.PORTKIT_CUTTING_TABLE
  ? (await import(pathToFileURL(process.env.PORTKIT_CUTTING_TABLE).href)).default
  : FALLBACK;
registerCuttingBoard(table);
const component = _startup()[table.component];

function withRandom(values, fn) {
  const original = Math.random;
  let i = 0;
  Math.random = () => values[i++ % values.length];
  try {
    return fn();
  } finally {
    Math.random = original;
  }
}

function fresh() {
  world._properties.clear();
  const dimension = _dimension();
  return { dimension, block: _block(dimension, "north") };
}

const interact = (block, dimension, player) => component.onPlayerInteract({ block, dimension, player });

// -- pure logic ---------------------------------------------------------------

test("rolls keep an item unless random > chance + fortune bonus", () => {
  const recipe = { results: [{ item: "a", count: 3, chance: 0.5 }, { item: "b", count: 1, chance: 0.1 }] };
  const rolls = [0.4, 0.6, 0.5, 0.15];
  let i = 0;
  const random = () => rolls[i++];
  // a: 0.4 keep, 0.6 lose, 0.5 keep (not > 0.5) -> 2; b: 0.15 > 0.1 lose
  assert.deepEqual(core.rollResults(recipe, 0, 0.1, random), [{ item: "a", count: 2 }]);
  i = 0;
  // Fortune II adds 0.2: a keeps all three, b keeps (0.15 <= 0.3)
  assert.deepEqual(core.rollResults(recipe, 2, 0.1, random), [{ item: "a", count: 3 }, { item: "b", count: 1 }]);
});

test("results spawn toward the facing turned counter-clockwise", () => {
  assert.deepEqual(core.spawnOffset("north"), { dx: -0.2, dy: 0.2, dz: 0, vx: -0.2, vy: 0, vz: 0 });
  assert.deepEqual(core.spawnOffset("east"), { dx: 0, dy: 0.2, dz: -0.2, vx: 0, vy: 0, vz: -0.2 });
  assert.deepEqual(core.spawnOffset("south"), { dx: 0.2, dy: 0.2, dz: 0, vx: 0.2, vy: 0, vz: 0 });
  assert.deepEqual(core.spawnOffset("west"), { dx: 0, dy: 0.2, dz: 0.2, vx: 0, vy: 0, vz: 0.2 });
});

test("a tool matches by item or by Bedrock tag", () => {
  const tool = { items: ["minecraft:iron_shovel"], tags: ["minecraft:is_shovel"] };
  assert.equal(core.toolMatches(tool, "minecraft:iron_shovel", () => false), true);
  assert.equal(core.toolMatches(tool, "other:shovel", (t) => t === "minecraft:is_shovel"), true);
  assert.equal(core.toolMatches(tool, "minecraft:stick", () => false), false);
});

test("the processing sound follows FD's order", () => {
  const t = FALLBACK;
  assert.deepEqual(core.processingSound(t, { sound: "use.wood" }, "x", true), { id: "use.wood", pitch: 1.0, volume: 1.0 });
  assert.equal(core.processingSound(t, { sound: null }, "minecraft:shears", false), null);
  assert.equal(core.processingSound(t, {}, "minecraft:shears", true).id, "mob.sheep.shear");
  assert.equal(core.processingSound(t, {}, "farmersdelight:iron_knife", true).volume, 0.8);
  assert.equal(core.processingSound(t, {}, "minecraft:iron_axe", true), null);
  assert.equal(core.processingSound(t, {}, "minecraft:iron_axe", false).id, "dig.wood");
});

test("the board takes a whole stack, or what fits of the same item", () => {
  assert.equal(core.amountToAdd(undefined, 64, 64, false), 64);
  assert.equal(core.amountToAdd({ amount: 60 }, 10, 64, true), 4);
  assert.equal(core.amountToAdd({ amount: 64 }, 10, 64, true), 0);
  assert.equal(core.amountToAdd({ amount: 1 }, 1, 1, false), 0);
});

test("unbreaking spares a use with chance level/(level+1)", () => {
  assert.equal(core.takesDamage(0, () => 0.99), true);
  assert.equal(core.takesDamage(1, () => 0.4), false);
  assert.equal(core.takesDamage(1, () => 0.5), true);
  assert.equal(core.takesDamage(3, () => 0.74), false);
});

// -- the table the converter wrote -------------------------------------------

test("the data table has the shape the runtime reads", () => {
  for (const key of ["component", "fortune_bonus", "messages", "recipes", "sound_tools", "sounds"]) {
    assert.ok(key in table, key);
  }
  const ids = new Set();
  for (const r of table.recipes) {
    assert.ok(!ids.has(r.id), `duplicate ${r.id}`);
    ids.add(r.id);
    assert.ok(r.ingredient.length > 0 && r.tool.items.length > 0 && r.results.length > 0, r.id);
    for (const res of r.results) assert.ok(res.count >= 1 && res.chance >= 0, r.id);
  }
  const gravel = table.recipes.find((r) => r.id === "farmersdelight:cutting/gravel");
  assert.ok(gravel.tool.items.includes("minecraft:iron_shovel") || gravel.tool.items.includes("minecraft:wooden_shovel"));
});

// -- the Bedrock binding -----------------------------------------------------

test("placing, cutting and taking back", () => {
  const { dimension, block } = fresh();
  const player = _player(dimension, new ItemStack("minecraft:gravel", 3));
  interact(block, dimension, player);
  assert.equal(player.held, undefined);
  assert.equal(dimension.sounds.at(-1).id, "place.wood");

  const shovel = new ItemStack("minecraft:wooden_shovel", 1);
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", shovel);
  // first roll keeps the gravel (0.05 <= 1), second keeps the flint (0.05 <= 0.1), damage roll irrelevant
  withRandom([0.05], () => interact(block, dimension, player));
  assert.deepEqual(dimension.spawned.map((e) => [e.stack.typeId, e.stack.amount]),
    [["minecraft:gravel", 1], ["minecraft:flint", 1]]);
  // facing north: west of centre, moving west
  assert.deepEqual(dimension.spawned[0].location, { x: 10.3, y: 64.2, z: -2.5 });
  assert.deepEqual(dimension.spawned[0].impulses, [{ x: -0.2, y: 0, z: 0 }]);
  assert.equal(shovel.getComponent("minecraft:durability").damage, 1);
  assert.deepEqual(player.actionbar.at(-1),
    { rawtext: [{ translate: table.messages.remaining, with: ["2"] }] });
  // gravel is a block item and the recipe names no sound: FD plays the block's
  // break sound, which scripts can't reach, so nothing.
  assert.equal(dimension.sounds.at(-1).id, "place.wood");

  player.getComponent("minecraft:equippable").setEquipment("Mainhand", undefined);
  interact(block, dimension, player);
  assert.deepEqual(player.inventory.map((s) => [s.typeId, s.amount]), [["minecraft:gravel", 2]]);
  assert.equal(dimension.sounds.at(-1).id, "hit.wood");
  assert.equal(world._properties.size, 0);
});

test("a tool no recipe takes says so and changes nothing", () => {
  const { dimension, block } = fresh();
  const player = _player(dimension, new ItemStack("minecraft:gravel", 1));
  interact(block, dimension, player);
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", new ItemStack("farmersdelight:iron_knife", 1));
  interact(block, dimension, player);
  assert.deepEqual(player.actionbar.at(-1), { rawtext: [{ translate: table.messages.no_recipe }] });
  assert.equal(dimension.spawned.length, 0);
  assert.equal(JSON.parse([...world._properties.values()][0]).amount, 1);
});

test("creative keeps the held stack and the tool takes no damage", () => {
  const { dimension, block } = fresh();
  const gravel = new ItemStack("minecraft:gravel", 5);
  const player = _player(dimension, gravel, { creative: true });
  interact(block, dimension, player);
  assert.equal(player.held, gravel);
  const shovel = new ItemStack("minecraft:iron_shovel", 1);
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", shovel);
  withRandom([0.5], () => interact(block, dimension, player));
  assert.equal(shovel.getComponent("minecraft:durability").damage, 0);
});

test("the last point of durability breaks the tool", () => {
  const { dimension, block } = fresh();
  const player = _player(dimension, new ItemStack("minecraft:gravel", 2));
  interact(block, dimension, player);
  const shovel = new ItemStack("minecraft:wooden_shovel", 1);
  shovel.getComponent("minecraft:durability").damage = 59;
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", shovel);
  withRandom([0.05], () => interact(block, dimension, player));
  assert.equal(player.held, undefined);
  assert.equal(dimension.sounds.at(-1).id, table.sounds.break.id);
});

test("breaking the board drops what it held; a new board starts empty", () => {
  const { dimension, block } = fresh();
  const named = new ItemStack("farmersdelight:cabbage", 4);
  named.nameTag = "Bob";
  const player = _player(dimension, named);
  interact(block, dimension, player);
  component.onPlayerBreak({ block, dimension, player });
  assert.equal(dimension.spawned.length, 1);
  assert.equal(dimension.spawned[0].stack.amount, 4);
  assert.equal(dimension.spawned[0].stack.nameTag, "Bob");
  world.setDynamicProperty(kit.storageKey(table.component, dimension.id, block.location), '{"id":"x","amount":1}');
  component.onPlace({ block, dimension });
  assert.equal(world._properties.size, 0);
});

test("a full inventory drops the taken stack at the player", () => {
  const { dimension, block } = fresh();
  const player = _player(dimension, new ItemStack("minecraft:gravel", 10), { inventoryRoom: 4 });
  interact(block, dimension, player);
  interact(block, dimension, player);
  assert.deepEqual(player.inventory.map((s) => s.amount), [4]);
  assert.deepEqual(dimension.spawned.map((e) => e.stack.amount), [6]);
});
