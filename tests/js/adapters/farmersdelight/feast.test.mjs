// The fixed feast runtime (src/portkit/adapters/farmersdelight/runtime), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/adapters/farmersdelight/feast.test.mjs
// (tests/adapters/farmersdelight/test_feasts.py runs it with PORTKIT_FEAST_TABLE set to a data table
// the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../../../src/portkit/adapters/farmersdelight/runtime/feast_core.js";
import { registerFeasts } from "../../../../src/portkit/adapters/farmersdelight/runtime/feast.js";
import { ItemStack, _dimension, _permutation, _player, _startup } from "@minecraft/server";

const FALLBACK = {
  component: "farmersdelight:portkit_feast",
  feasts: {
    "farmersdelight:roast_chicken_block": {
      container: "minecraft:bowl", container_name: "item.bowl.name", leftovers: true, max_servings: 4,
      servings: Array(4).fill("farmersdelight:roast_chicken"),
    },
    "farmersdelight:stuffed_pumpkin_block": {
      container: "minecraft:bowl", container_name: "item.bowl.name", leftovers: false, max_servings: 4,
      servings: Array(4).fill("farmersdelight:stuffed_pumpkin"),
    },
    "farmersdelight:rice_roll_medley_block": {
      container: null, container_name: null, leftovers: true, max_servings: 8,
      servings: ["farmersdelight:cod_roll", "farmersdelight:cod_roll", "farmersdelight:salmon_roll",
        "farmersdelight:salmon_roll", "farmersdelight:salmon_roll", "farmersdelight:kelp_roll_slice",
        "farmersdelight:kelp_roll_slice", "farmersdelight:kelp_roll_slice"],
    },
  },
  messages: { use_container: "tile.farmersdelight:feast.use_container.name" },
  servings_state: "farmersdelight:servings",
  sounds: {
    clear: { id: "dig.wood", pitch: 0.8, volume: 0.8 },
    serve: { id: "armor.equip_generic", pitch: 1.0, volume: 1.0 },
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_FEAST_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerFeasts(table);
const component = _startup()[table.component];
const CHICKEN = "farmersdelight:roast_chicken_block";
const PUMPKIN = "farmersdelight:stuffed_pumpkin_block";
const MEDLEY = "farmersdelight:rice_roll_medley_block";

function feastBlock(dimension, typeId, servings, location = { x: 3, y: 64, z: -2 }) {
  return {
    dimension,
    location,
    typeId,
    permutation: _permutation(typeId, { "minecraft:cardinal_direction": "north", [table.servings_state]: servings }),
    setPermutation(p) { this.permutation = p; },
  };
}

function use(typeId, servings, held, options) {
  const dimension = _dimension();
  const block = feastBlock(dimension, typeId, servings);
  const player = _player(dimension, held, options);
  component.onPlayerInteract({ block, dimension, player });
  return { block, dimension, player };
}

test("the component is registered under the table's id", () => {
  assert.equal(typeof component.onPlayerInteract, "function");
});

const has = (id) => ({ skip: table.feasts[id] ? false : `${id} not in this table` });

test("the medley serves cod, cod, salmon x3, kelp slice x3 by serving count", has(MEDLEY), () => {
  const medley = table.feasts[MEDLEY];
  assert.deepEqual([8, 7, 6, 5, 4, 3, 2, 1].map((n) => core.servingAt(medley, n).split(":")[1]),
    ["kelp_roll_slice", "kelp_roll_slice", "kelp_roll_slice", "salmon_roll", "salmon_roll", "salmon_roll",
      "cod_roll", "cod_roll"]);
});

test("a bowl takes one serving: state down, bowl used up, serving given, sound", () => {
  const bowls = new ItemStack("minecraft:bowl", 3);
  const { block, dimension, player } = use(CHICKEN, 4, bowls);
  assert.equal(block.permutation.getState(table.servings_state), 3);
  assert.equal(player.held.amount, 2);
  assert.deepEqual(player.inventory.map((s) => [s.typeId, s.amount]), [["farmersdelight:roast_chicken", 1]]);
  assert.deepEqual(dimension.sounds.map((s) => s.id), [table.sounds.serve.id]);
  assert.deepEqual(dimension.commands, []);
});

test("the last bowl empties the hand; creative keeps it", () => {
  const one = use(CHICKEN, 2, new ItemStack("minecraft:bowl", 1));
  assert.equal(one.player.held, undefined);
  const creative = use(CHICKEN, 2, new ItemStack("minecraft:bowl", 1), { creative: true });
  assert.equal(creative.player.held.amount, 1);
  assert.equal(creative.block.permutation.getState(table.servings_state), 1);
});

test("the wrong item asks for the container and changes nothing", () => {
  const { block, dimension, player } = use(CHICKEN, 4, new ItemStack("minecraft:stick", 1));
  assert.equal(block.permutation.getState(table.servings_state), 4);
  assert.equal(player.inventory.length, 0);
  assert.deepEqual(dimension.sounds, []);
  assert.deepEqual(player.actionbar, [{ rawtext: [{ translate: table.messages.use_container,
    with: { rawtext: [{ translate: "item.bowl.name" }] } }] }]);
  const empty = use(CHICKEN, 4, undefined);
  assert.equal(empty.block.permutation.getState(table.servings_state), 4);
});

test("a feast with leftovers lingers at 0, and the next use clears it through its loot", () => {
  const last = use(CHICKEN, 1, new ItemStack("minecraft:bowl", 1));
  assert.equal(last.block.permutation.getState(table.servings_state), 0);
  assert.deepEqual(last.dimension.commands, []);
  const clear = use(CHICKEN, 0, new ItemStack("minecraft:bowl", 1));
  assert.deepEqual(clear.dimension.commands, ["setblock 3 64 -2 air destroy"]);
  assert.deepEqual(clear.dimension.sounds.map((s) => [s.id, s.volume, s.pitch]),
    [[table.sounds.clear.id, 0.8, 0.8]]);
  assert.equal(clear.player.held.amount, 1);
  assert.equal(clear.player.inventory.length, 0);
});

test("a feast without leftovers vanishes with its last serving", has(PUMPKIN), () => {
  const { block, dimension, player } = use(PUMPKIN, 1, new ItemStack("minecraft:bowl", 2));
  assert.equal(block.permutation.getState(table.servings_state), 0);
  assert.deepEqual(dimension.commands, ["setblock 3 64 -2 air destroy"]);
  assert.equal(player.inventory[0].typeId, "farmersdelight:stuffed_pumpkin");
  const early = use(PUMPKIN, 2, new ItemStack("minecraft:bowl", 2));
  assert.deepEqual(early.dimension.commands, []);
});

test("servings with no container serve to any hand and use nothing up", has(MEDLEY), () => {
  const stick = new ItemStack("minecraft:stick", 5);
  const { block, player } = use(MEDLEY, 8, stick);
  assert.equal(block.permutation.getState(table.servings_state), 7);
  assert.equal(player.held.amount, 5);
  assert.equal(player.inventory[0].typeId, "farmersdelight:kelp_roll_slice");
  const empty = use(MEDLEY, 1, undefined);
  assert.equal(empty.player.inventory[0].typeId, "farmersdelight:cod_roll");
  assert.deepEqual(empty.dimension.commands, []);
});

test("a full inventory drops the serving at the player", () => {
  const { player, dimension } = use(CHICKEN, 3, new ItemStack("minecraft:bowl", 1), { inventoryRoom: 0 });
  assert.equal(player.inventory.length, 0);
  assert.equal(dimension.spawned[0].stack.typeId, "farmersdelight:roast_chicken");
});

test("blocks the table doesn't hold and states out of range do nothing", () => {
  const other = use("farmersdelight:cooking_pot", 4, new ItemStack("minecraft:bowl", 1));
  assert.deepEqual(other.dimension.sounds, []);
  assert.equal(core.interaction(table.feasts[CHICKEN], 9, "minecraft:bowl").action, "none");
  assert.equal(core.interaction(table.feasts[CHICKEN], undefined, "minecraft:bowl").action, "none");
});
