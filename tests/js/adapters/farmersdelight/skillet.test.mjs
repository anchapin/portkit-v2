// The fixed skillet runtime (src/portkit/adapters/farmersdelight/runtime), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/adapters/farmersdelight/skillet.test.mjs
// (tests/adapters/farmersdelight/test_skillet.py runs it with PORTKIT_SKILLET_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../../../src/portkit/adapters/farmersdelight/runtime/skillet_core.js";
import { registerSkillet } from "../../../../src/portkit/adapters/farmersdelight/runtime/skillet.js";
import {
  GameMode, ItemStack, _dimension, _fire, _flush, _permutation, _player, _runIntervals, _startup, world,
} from "@minecraft/server";

const FALLBACK = {
  block: "farmersdelight:skillet",
  component: "farmersdelight:portkit_skillet",
  cooking: { default_cooking_time: 600, fire_aspect_step: 0.05, min_cooking_time: 60, reduction: 0.2 },
  heat: {
    sources: [{ id: "minecraft:campfire", states: { extinguished: false } }, { id: "minecraft:magma" }],
    conductors: [{ id: "minecraft:hopper" }],
    tray: [{ id: "minecraft:campfire" }],
    nearby: [{ id: "minecraft:campfire" }, { id: "minecraft:magma" }],
  },
  item: "farmersdelight:skillet",
  launch: { dy: 0.3, speed: 0.08, up: 0.25 },
  messages: {
    invalid_item: "tile.farmersdelight:skillet.invalid_item",
    underwater: "item.farmersdelight:skillet.underwater",
    how_to_cook: "item.farmersdelight:skillet.how_to_cook",
  },
  recipes: [
    { id: "minecraft:cooked_beef_from_campfire_cooking", ingredient: ["minecraft:beef"],
      result: { item: "minecraft:cooked_beef", count: 1 }, cookingtime: 600 },
  ],
  sounds: {
    add_food: { id: "farmersdelight:block.skillet.add_food", pitch: 1.0, volume: 0.8 },
    attack: { id: "farmersdelight:item.skillet.attack.strong", pitch: 1.0, pitch_max: 1.1, pitch_min: 0.9, volume: 1.0 },
    held_sizzle: { chance_per_tick: 0.02, id: "farmersdelight:block.skillet.sizzle", pitch: 1.0, pitch_max: 1.1,
      pitch_min: 0.9, volume: 0.4 },
    place: { id: "block.lantern.place", pitch: 1.0, volume: 0.7 },
    sizzle: { chance_per_tick: 0.1, id: "farmersdelight:block.skillet.sizzle", pitch: 1.0, pitch_max: 1.1,
      pitch_min: 0.9, volume: 0.4 },
  },
  support_state: "farmersdelight:support",
  tick_interval: 10,
};

async function loadTable() {
  const path = process.env.PORTKIT_SKILLET_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerSkillet(table);
const component = _startup()[table.component];
const RULE = table.cooking;
const beefRecipe = core.findRecipe(table.recipes, "minecraft:beef");
const BEEF_TIME = beefRecipe ? core.cookingTime(beefRecipe.cookingtime, 0, RULE) : 0;

const CAMPFIRE = { id: "minecraft:campfire", states: { extinguished: false } };
const UNLIT_CAMPFIRE = { id: "minecraft:campfire", states: { extinguished: true } };

/** A placed skillet with `below` ([{ id, states }] downward). */
function skilletBlock(dimension, { facing = "north", support = "false", below = [], location = { x: 1, y: 70, z: 2 } } = {}) {
  const block = {
    dimension,
    location,
    typeId: table.block,
    permutation: _permutation(table.block, { "minecraft:cardinal_direction": facing, [table.support_state]: support }),
    setPermutation(p) { this.permutation = p; },
  };
  block.below = (steps = 1) => {
    const entry = below[steps - 1];
    if (!entry) return { typeId: "minecraft:air", permutation: _permutation("minecraft:air") };
    return { typeId: entry.id, permutation: _permutation(entry.id, entry.states ?? {}) };
  };
  return block;
}

/** A player with an off-hand, dynamic properties and a world around it ({ "x,y,z": block }). */
function fullPlayer(dimension, held, { offhand, creative = false, blocks = {}, head = "minecraft:air", sneaking = false,
  onFire = false } = {}) {
  const player = _player(dimension, held, { creative });
  const slots = { Mainhand: held, Offhand: offhand };
  const props = new Map();
  Object.assign(player, {
    typeId: "minecraft:player",
    isSneaking: sneaking,
    location: { x: 0.5, y: 64, z: 0.5 },
    getDynamicProperty: (k) => props.get(k),
    setDynamicProperty: (k, v) => (v === undefined ? props.delete(k) : props.set(k, v)),
    getHeadLocation: () => ({ x: 0.5, y: 65.6, z: 0.5 }),
    _props: props,
  });
  const base = player.getComponent.bind(player);
  player.getComponent = (id) => {
    if (id === "minecraft:equippable") return { getEquipment: (s) => slots[s], setEquipment: (s, v) => { slots[s] = v; } };
    if (id === "minecraft:onfire") return onFire ? { onFireTicksRemaining: 20 } : undefined;
    return base(id);
  };
  Object.defineProperty(player, "held", { get: () => slots.Mainhand });
  Object.defineProperty(player, "offhand", { get: () => slots.Offhand, set: (v) => { slots.Offhand = v; } });
  dimension.getBlock = (at) => {
    if (!Number.isInteger(at.y)) return { typeId: head, permutation: _permutation(head), isWaterlogged: false };
    const key = `${at.x},${at.y},${at.z}`;
    const entry = blocks[key];
    return entry ? { typeId: entry.id, permutation: _permutation(entry.id, entry.states ?? {}) }
      : { typeId: "minecraft:air", permutation: _permutation("minecraft:air") };
  };
  world._players.length = 0;
  world._players.push(player);
  return player;
}

function skilletItem(enchantments = []) {
  const stack = new ItemStack(table.item, 1);
  for (const e of enchantments) stack._enchantments.push(e);
  return stack;
}

function place(dimension, block, player) {
  const event = { block, dimension, player, permutationToPlace: block.permutation, cancel: false };
  component.beforeOnPlayerPlace(event);
  if (!event.cancel) {
    block.permutation = event.permutationToPlace;
    component.onPlace({ block, dimension, previousBlock: { type: { id: "minecraft:air" } } });
  }
  return event;
}

test("cooking time: a fifth of the recipe's in whole seconds, Fire Aspect shortens it, 3 s minimum", () => {
  assert.equal(core.cookingTime(600, 0, RULE), 120);
  assert.equal(core.cookingTime(600, 1, RULE), 80); // 30 s x 0.15 = 4.5 -> 4 s
  assert.equal(core.cookingTime(600, 2, RULE), 60);
  assert.equal(core.cookingTime(600, 3, RULE), 60); // 1 s, clamped up to 3 s
  assert.equal(core.cookingTime(100, 0, RULE), 60); // 1 s, clamped up
  assert.equal(core.cookingTime(1200, 0, RULE), 240);
});

test("step: heated cooks one item per total, unheated cools by 2 a tick", () => {
  const skillet = core.emptySkillet();
  core.insert(skillet, { id: "minecraft:beef" }, 2, 64, FALLBACK.recipes[0], RULE);
  assert.equal(skillet.cookTimeTotal, 120);
  let cooked = [];
  for (let i = 0; i < 12; i += 1) cooked = cooked.concat(core.step(skillet, { heated: true, interval: 10, recipes: FALLBACK.recipes }).cooked);
  assert.deepEqual(cooked, [{ id: "minecraft:cooked_beef", amount: 1 }]);
  assert.equal(skillet.stack.amount, 1);
  core.step(skillet, { heated: true, interval: 10, recipes: FALLBACK.recipes });
  core.step(skillet, { heated: false, interval: 3, recipes: FALLBACK.recipes });
  assert.equal(skillet.cookTime, 4);
  core.step(skillet, { heated: false, interval: 10, recipes: FALLBACK.recipes });
  assert.equal(skillet.cookTime, 0);
});

test("launch: thrown toward the side clockwise of the facing", () => {
  assert.deepEqual(core.launch("north", FALLBACK.launch), { dx: 0.5, dy: 0.3, dz: 0.5, vx: 0.08, vy: 0.25, vz: 0 });
  assert.equal(core.launch("east", FALLBACK.launch).vz, 0.08);
  assert.equal(core.launch("south", FALLBACK.launch).vx, -0.08);
  assert.equal(core.launch("west", FALLBACK.launch).vz, -0.08);
});

test("placed: food goes in whole, another item is refused, an empty hand takes the stack", { skip: !beefRecipe }, () => {
  const dimension = _dimension();
  const block = skilletBlock(dimension, { below: [CAMPFIRE] });
  const player = fullPlayer(dimension, skilletItem(), { sneaking: true });
  place(dimension, block, player);
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", new ItemStack("minecraft:beef", 5));
  component.onPlayerInteract({ block, dimension, player });
  assert.equal(player.held, undefined);
  assert.deepEqual(dimension.sounds.map((s) => s.id), [table.sounds.add_food, table.sounds.place].filter(Boolean).map((s) => s.id));
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", new ItemStack("minecraft:beef", 3));
  component.onPlayerInteract({ block, dimension, player });
  assert.equal(player.held.amount, 3, "a full skillet takes nothing more");
  if (table.messages.invalid_item) {
    assert.deepEqual(player.actionbar.at(-1), { rawtext: [{ translate: table.messages.invalid_item }] });
  }
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", undefined);
  component.onPlayerInteract({ block, dimension, player });
  assert.equal(player.held.typeId, "minecraft:beef");
  assert.equal(player.held.amount, 5);
});

test("placed: in creative the held stack stays and a taken stack is gone", { skip: !beefRecipe }, () => {
  const dimension = _dimension();
  const block = skilletBlock(dimension, { location: { x: 9, y: 70, z: 9 } });
  const player = fullPlayer(dimension, new ItemStack("minecraft:beef", 4), { creative: true });
  component.onPlace({ block, dimension, previousBlock: { type: { id: "minecraft:air" } } });
  component.onPlayerInteract({ block, dimension, player });
  assert.equal(player.held.amount, 4);
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", undefined);
  component.onPlayerInteract({ block, dimension, player });
  assert.equal(player.held, undefined);
});

test("tick: over a lit campfire each item cooks and is thrown out; unlit it doesn't; the tray follows below", { skip: !beefRecipe }, () => {
  const dimension = _dimension();
  const below = [CAMPFIRE];
  const block = skilletBlock(dimension, { below, location: { x: 3, y: 70, z: 3 } });
  const player = fullPlayer(dimension, skilletItem(), { sneaking: true });
  const event = place(dimension, block, player);
  assert.equal(event.cancel, false);
  assert.equal(block.permutation.getState(table.support_state), "true", "a campfire is a tray heat source");
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", new ItemStack("minecraft:beef", 2));
  component.onPlayerInteract({ block, dimension, player });
  for (let t = 0; t < BEEF_TIME; t += table.tick_interval) component.onTick({ block, dimension });
  assert.equal(dimension.spawned.length, 1);
  assert.equal(dimension.spawned[0].stack.typeId, beefRecipe.result.item);
  assert.deepEqual(dimension.spawned[0].impulses, [{ x: 0.08, y: 0.25, z: 0 }]);
  below[0] = UNLIT_CAMPFIRE;
  for (let t = 0; t < BEEF_TIME * 2; t += table.tick_interval) component.onTick({ block, dimension });
  assert.equal(dimension.spawned.length, 1, "an unlit campfire doesn't heat");
  below.length = 0;
  component.onTick({ block, dimension });
  assert.equal(block.permutation.getState(table.support_state), "false");
});

test("placing: only while sneaking; the placed skillet's Fire Aspect shortens its cooking", { skip: !beefRecipe }, () => {
  const dimension = _dimension();
  const block = skilletBlock(dimension, { below: [CAMPFIRE], location: { x: 5, y: 70, z: 5 } });
  const standing = fullPlayer(dimension, skilletItem(), { blocks: { "0,63,0": CAMPFIRE } });
  const refused = place(dimension, block, standing);
  assert.equal(refused.cancel, true);
  _flush();
  if (table.messages.how_to_cook) {
    assert.deepEqual(standing.actionbar.at(-1), { rawtext: [{ translate: table.messages.how_to_cook }] });
  }
  const sneaking = fullPlayer(dimension, skilletItem([{ id: "fire_aspect", level: 1 }]), { sneaking: true });
  place(dimension, block, sneaking);
  sneaking.getComponent("minecraft:equippable").setEquipment("Mainhand", new ItemStack("minecraft:beef", 1));
  component.onPlayerInteract({ block, dimension, player: sneaking });
  const stored = JSON.parse(world.getDynamicProperty(`${table.component}|minecraft:overworld|5,70,5`));
  assert.equal(stored.cookTimeTotal, core.cookingTime(beefRecipe.cookingtime, 1, RULE));
  assert.deepEqual(stored.item.enchantments, [{ id: "fire_aspect", level: 1 }]);
});

test("breaking: the stack drops and the plain drop is swapped for the placed skillet", { skip: !beefRecipe }, () => {
  const dimension = _dimension();
  const block = skilletBlock(dimension, { location: { x: 7, y: 70, z: 7 } });
  const player = fullPlayer(dimension, skilletItem([{ id: "sharpness", level: 2 }]), { sneaking: true });
  place(dimension, block, player);
  player.getComponent("minecraft:equippable").setEquipment("Mainhand", new ItemStack("minecraft:beef", 3));
  component.onPlayerInteract({ block, dimension, player });
  const plain = { location: { x: 7.5, y: 70.2, z: 7.5 }, removed: false, remove() { this.removed = true; },
    getComponent: (id) => (id === "minecraft:item" ? { itemStack: new ItemStack(table.item, 1) } : undefined) };
  dimension.getEntities = () => [plain];
  component.onPlayerBreak({ block, dimension, player });
  assert.equal(dimension.spawned[0].stack.typeId, "minecraft:beef");
  assert.equal(dimension.spawned[0].stack.amount, 3);
  _flush();
  assert.equal(plain.removed, true);
  const swapped = dimension.spawned[1].stack;
  assert.equal(swapped.typeId, table.item);
  assert.deepEqual(swapped._enchantments, [{ id: "sharpness", level: 2 }]);
});

test("held: off-hand skillet, food in the main hand near heat cooks one instead of eating it", { skip: !beefRecipe }, () => {
  const dimension = _dimension();
  // An unlit campfire next to the player counts (the tag alone, Item#isPlayerNearHeatSource).
  const player = fullPlayer(dimension, new ItemStack("minecraft:beef", 3),
    { offhand: skilletItem(), blocks: { "1,64,0": UNLIT_CAMPFIRE } });
  const event = _fire("before", "itemUse", { source: player, itemStack: player.held, cancel: false });
  assert.equal(event.cancel, true);
  _flush();
  assert.equal(player.held.amount, 2);
  let given = 0;
  for (let t = 0; t < BEEF_TIME; t += table.tick_interval) {
    _runIntervals();
    given = player.inventory.length;
    if (given) break;
  }
  assert.equal(given, 1);
  assert.equal(player.inventory[0].typeId, beefRecipe.result.item);
  assert.equal(player._props.size, 0, "the session ends");
});

test("held: taking the skillet out of the off-hand gives the food back", { skip: !beefRecipe }, () => {
  const dimension = _dimension();
  const player = fullPlayer(dimension, new ItemStack("minecraft:beef", 1), { offhand: skilletItem(), onFire: true });
  _fire("before", "itemUse", { source: player, itemStack: player.held, cancel: false });
  _flush();
  assert.equal(player.held, undefined);
  _runIntervals();
  player.offhand = undefined;
  _runIntervals();
  assert.equal(player.inventory.length, 1);
  assert.equal(player.inventory[0].typeId, "minecraft:beef");
});

test("held: away from heat the food is eaten as usual; underwater it says so", { skip: !beefRecipe }, () => {
  const dimension = _dimension();
  const cold = fullPlayer(dimension, new ItemStack("minecraft:beef", 1), { offhand: skilletItem() });
  assert.equal(_fire("before", "itemUse", { source: cold, itemStack: cold.held, cancel: false }).cancel, false);
  const wet = fullPlayer(dimension, new ItemStack("minecraft:beef", 1),
    { offhand: skilletItem(), onFire: true, head: "minecraft:water" });
  _fire("before", "itemUse", { source: wet, itemStack: wet.held, cancel: false });
  _flush();
  assert.equal(wet.held.amount, 1);
  if (table.messages.underwater) assert.deepEqual(wet.actionbar.at(-1), { rawtext: [{ translate: table.messages.underwater }] });
});

test("hitting with the skillet plays FD's strong hit sound", () => {
  const dimension = _dimension();
  const player = fullPlayer(dimension, skilletItem());
  _fire("after", "entityHitEntity", { damagingEntity: player, hitEntity: {} });
  if (table.sounds.attack) {
    assert.equal(dimension.sounds.at(-1).id, table.sounds.attack.id);
    assert.ok(dimension.sounds.at(-1).pitch >= 0.9 && dimension.sounds.at(-1).pitch <= 1.1);
  }
  const fists = fullPlayer(_dimension(), undefined);
  _fire("after", "entityHitEntity", { damagingEntity: fists, hitEntity: {} });
  assert.equal(fists.dimension.sounds.length, 0);
});

test("the held loop runs at the table's tick interval", () => {
  assert.deepEqual(_runIntervals(), [table.tick_interval]);
});
