// The fixed waystone runtime's warp stone (src/portkit/runtime), offline under node.
// Run: node --import ./tests/js/register.mjs --test tests/js/warp_stone.test.mjs
// (tests/test_waystones.py runs it with PORTKIT_WAYSTONE_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../src/portkit/runtime/waystone_core.js";
import { registerWaystones } from "../../src/portkit/runtime/waystone.js";
import { _fire, _flush, _permutation, _runIntervals, _startup, world, GameMode, ItemStack } from "@minecraft/server";
import { _reset, _respond, _shown } from "@minecraft/server-ui";

const REQUIREMENTS = [
  { args: ["distance", 0.01], fn: "scaled_add_xp_cost", when: { is_interdimensional: false } },
  { args: [27], fn: "add_xp_cost", when: { is_interdimensional: true } },
  { args: [0], fn: "min_xp_cost", when: {} },
  { args: [27], fn: "max_xp_cost", when: {} },
];
// The defaults have no warp stone rule: the distance cost applies.
const BY_TYPE = {
  "waystones:waystone": REQUIREMENTS,
  "waystones:orange_sharestone": REQUIREMENTS,
  "waystones:warp_portal": REQUIREMENTS,
};

const FALLBACK = {
  block_types: { "waystones:waystone": "waystones:waystone", "waystones:orange_sharestone": "waystones:orange_sharestone" },
  blocks: ["waystones:orange_sharestone", "waystones:waystone"],
  component: "waystones:portkit_waystone",
  default_type: "waystones:waystone",
  half_state: "waystones:half",
  messages: {
    activated: "chat.waystones.waystone_activated",
    current_location: "gui.waystones.waystone_selection.current_location",
    missing: "chat.waystones.waystone_missing",
    none: "gui.waystones.waystone_selection.no_waystones_activated",
    none_shared: "gui.waystones.waystone_selection.no_sharestones_available",
    not_enough_xp: "chat.waystones.not_enough_xp",
    out_of_range: "chat.waystones.source_waystone_out_of_range",
    return_to_portal: "gui.waystones.waystone_selection.return_to_portal",
    title: "container.waystones.waystone_selection",
    unnamed: "gui.waystones.waystone_selection.unnamed_waystone",
    xp_cost: "gui.waystones.waystone_selection.xp_requirement",
  },
  name_max_length: 128,
  namespace: "waystones",
  networks: {
    "waystones:orange_sharestone": { name: "sharestone_name", none: "none_shared", requirements: REQUIREMENTS, shared: true },
    "waystones:waystone": { name: "waystone_name", none: "none", requirements: REQUIREMENTS, shared: false },
  },
  portstones: {},
  range_sq: 64,
  restricted_origins: ["PLAYER"],
  rune_blocks: [],
  rune_state: "waystones:runes",
  sounds: {
    activate: { id: "random.levelup", pitch: 1.0, volume: 0.2 },
    arrive: { id: "portal.travel", pitch: 1.0, volume: 0.05 },
    depart: { id: "portal.travel", pitch: 1.0, volume: 0.01 },
    item_break: { id: "random.break", pitch: 0.8, spread: 0.4, volume: 0.8 },
    portal_close: { id: "random.fizz", pitch: 1.2, volume: 0.5 },
    portal_open: { id: "portal.travel", pitch: 1.4, volume: 0.25 },
    scroll_start: { id: "portal.trigger", pitch: 2.0, volume: 0.1 },
  },
  warp_portals: {
    blocks: ["waystones:warp_portal"],
    component: "waystones:portkit_warp_portal",
    cooldown: 20,
    deny: ["minecraft:wither"],
    error_style: "\u00a74",
    lifetime: 6000,
    requirements: REQUIREMENTS,
    return_property: "waystones:portkit_return_portal",
    return_requirements: { "waystones:waystone": REQUIREMENTS, "waystones:orange_sharestone": REQUIREMENTS },
    scroll: {
      items: ["waystones:portal_scroll"],
      network: "waystones:waystone",
      requirements: REQUIREMENTS,
      title: "container.waystones.waystone_selection",
      use_time: 32,
    },
    type: "waystones:warp_portal",
  },
  warp_stones: {
    durability: true,
    error_style: "\u00a74",
    items: { "waystones:warp_stone": { requirements: BY_TYPE } },
    network: "waystones:waystone",
    title: "container.waystones.waystone_selection",
    use_time: 32,
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_WAYSTONE_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerWaystones(table);
const stones = table.warp_stones;
_startup();
const STONE = Object.keys(stones.items)[0];
const HALF = table.half_state;
const WAYSTONE = Object.keys(table.block_types).find((id) => table.block_types[id] === stones.network);
const settle = () => new Promise((resolve) => setImmediate(resolve));

// -- a tiny world: stone at y <= 63, air above ------------------------------------

function makeDimension(id) {
  const blocks = new Map();
  const dimension = {
    id,
    sounds: [],
    spawned: [],
    entities: [],
    key: (p) => `${p.x},${p.y},${p.z}`,
    getBlock: (location) => blockAt(location),
    getEntities() { return []; },
    playSound(soundId, location, options) { dimension.sounds.push({ id: soundId, location, ...options }); },
    spawnItem(stack, location) { dimension.spawned.push({ stack, location }); return {}; },
    set(location, typeId, states) { blocks.set(dimension.key(location), _permutation(typeId, states)); },
  };
  function permutationAt(loc) {
    return blocks.get(dimension.key(loc)) ?? _permutation(loc.y <= 63 ? "minecraft:stone" : "minecraft:air");
  }
  function blockAt(location) {
    const loc = { x: location.x, y: location.y, z: location.z };
    return {
      dimension,
      location: loc,
      get permutation() { return permutationAt(loc); },
      get typeId() { return this.permutation.type.id; },
      get isAir() { return this.typeId === "minecraft:air"; },
      get isLiquid() { return this.typeId === "minecraft:water"; },
      below() { return blockAt({ ...loc, y: loc.y - 1 }); },
      above() { return blockAt({ ...loc, y: loc.y + 1 }); },
      setPermutation(p) { blocks.set(dimension.key(loc), p); },
      setType(typeId) { blocks.set(dimension.key(loc), _permutation(typeId)); },
    };
  }
  dimension.blockAt = blockAt;
  world._dimensions.set(id, dimension);
  return dimension;
}

let nextId = 900;
const SLOTS = 36;

/** A player holding `held` (an ItemStack or undefined) in slot 0, with `free` empty slots of SLOTS. */
function makePlayer(dimension, { held, xp = 0, creative = false, free = SLOTS - 1, location } = {}) {
  const slots = new Array(SLOTS).fill(undefined);
  slots[0] = held;
  for (let i = SLOTS - 1, filled = SLOTS - 1 - free; filled > 0; i--, filled--) {
    slots[i] = new ItemStack("minecraft:dirt", 64);
  }
  const props = {};
  const container = {
    get emptySlotsCount() { return slots.filter((s) => !s).length; },
    getItem: (i) => slots[i],
    setItem: (i, v) => { slots[i] = v; },
    addItem(stack) {
      const at = slots.findIndex((s) => !s);
      if (at === -1) return stack;
      slots[at] = stack;
      return undefined;
    },
  };
  const player = {
    id: String(nextId++),
    typeId: "minecraft:player",
    name: "Alex",
    dimension,
    location: location ?? { x: 0.5, y: 64, z: 0.5 },
    isValid: true,
    isSneaking: false,
    xp,
    actionbar: [],
    chat: [],
    teleports: [],
    slots,
    selectedSlotIndex: 0,
    getRotation: () => ({ x: 12, y: 0 }),
    getViewDirection: () => ({ x: 0, y: 0, z: 1 }),
    getTotalXp() { return this.xp; },
    addExperience(n) { this.xp += n; return this.xp; },
    getGameMode: () => (creative ? GameMode.Creative : GameMode.Survival),
    sendMessage(m) { this.chat.push(m); },
    onScreenDisplay: { setActionBar: (m) => player.actionbar.push(m) },
    getDynamicProperty: (key) => props[key],
    setDynamicProperty: (key, value) => { props[key] = value; },
    getComponent(id) { return id === "minecraft:inventory" ? { container } : undefined; },
    teleport(to, options) {
      this.teleports.push({ location: to, ...options });
      this.location = { ...to };
      if (options && options.dimension) this.dimension = options.dimension;
    },
  };
  return player;
}

function clearWorld() {
  for (const key of world.getDynamicPropertyIds()) world.setDynamicProperty(key, undefined);
  _reset();
}

/** A waystone-type block at `pos` facing north, stored (activated for each of `players`). */
function place(dimension, pos, typeId, name, ...players) {
  dimension.set(pos, typeId, { [HALF]: "lower", "minecraft:cardinal_direction": "north" });
  dimension.set({ ...pos, y: pos.y + 1 }, typeId, { [HALF]: "upper", "minecraft:cardinal_direction": "north" });
  const uid = `w${nextId++}`;
  world.setDynamicProperty(core.recordKey("waystones", dimension.id, pos), JSON.stringify({
    uid, type: table.block_types[typeId], order: nextId, dimension: dimension.id, pos, facing: "north",
    name: { text: name }, owner: null, origin: "PLAYER" }));
  for (const player of players) {
    const raw = player.getDynamicProperty(core.activatedKey("waystones"));
    const list = raw ? JSON.parse(raw) : [];
    player.setDynamicProperty(core.activatedKey("waystones"), JSON.stringify([...list, uid]));
  }
  return uid;
}

function use(player) {
  _fire("after", "itemUse", { source: player, itemStack: player.slots[player.selectedSlotIndex] });
}

async function hold(player, ticks = stones.use_time) {
  use(player);
  for (let i = 0; i < ticks; i++) _runIntervals();
  _flush();
  await settle();
}

const W = { x: 100, y: 64, z: 0 };
const W2 = { x: 20, y: 64, z: 0 };
const BESIDE_W = { x: 100.5, y: 64.5, z: -0.5 };
const START = { x: 0.5, y: 64, z: 0.5 };
const error = (key) => ({ rawtext: [{ text: "\u00a74" }, { translate: key }] });
const costTo = (pos) => core.cost(stones.items[STONE].requirements[stones.network],
  { is_interdimensional: false, distance: core.distance(START, pos) });
const damageOf = (stack) => stack.getComponent("minecraft:durability").damage;

function worn(damage) {
  const stack = new ItemStack(STONE, 1);
  stack.getComponent("minecraft:durability").damage = damage;
  return stack;
}

// -- core ----------------------------------------------------------------------

test("a stack breaks when one more damage reaches its maximum", () => {
  assert.equal(core.wearBreaks(0, 128), false);
  assert.equal(core.wearBreaks(126, 128), false);
  assert.equal(core.wearBreaks(127, 128), true);
});

// -- the warp stone ----------------------------------------------------------------

test("a warp stone held for its use time opens the activated waystones; a choice teleports, costs xp and one durability", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(STONE, 1), xp: 30 });
  place(overworld, W, WAYSTONE, "Home", alex);
  use(alex);
  assert.deepEqual(overworld.sounds.at(-1), { id: "portal.trigger", location: alex.location, volume: 0.1, pitch: 2.0 });
  for (let i = 0; i < stones.use_time - 1; i++) _runIntervals();
  _flush();
  assert.equal(_shown.length, 0);
  _runIntervals();
  _respond({ canceled: false, selection: 0 });
  _flush();
  await settle();
  const form = _shown.at(-1);
  assert.deepEqual(form.title, { translate: "container.waystones.waystone_selection" });
  assert.equal(form.body, ""); // no waystone in use: no "Current Location"
  const points = costTo(W);
  assert.ok(points > 0); // the defaults have no warp stone rule
  const label = form.buttons[0].text.rawtext;
  assert.deepEqual(label.slice(0, 2), [{ text: "Home" }, { text: "\n" }]);
  assert.ok(JSON.stringify(label[2]).includes(table.messages.xp_cost));
  assert.ok(JSON.stringify(label[2]).includes(`"text":"${points}"`));
  assert.deepEqual(alex.location, BESIDE_W);
  assert.equal(alex.xp, 30 - points);
  assert.equal(alex.slots[0].typeId, STONE);
  assert.equal(damageOf(alex.slots[0]), 1);
});

test("the last durability breaks the warp stone with the item break sound", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: worn(126), xp: 30 });
  place(overworld, W, WAYSTONE, "Home", alex);
  _respond({ canceled: false, selection: 0 });
  await hold(alex);
  assert.equal(damageOf(alex.slots[0]), 127);
  _respond({ canceled: false, selection: 0 });
  await hold(alex);
  assert.equal(alex.teleports.length, 2);
  assert.equal(alex.slots[0], undefined);
  const sound = alex.dimension.sounds.find((s) => s.id === "random.break");
  assert.ok(sound);
  assert.equal(sound.volume, 0.8);
  assert.ok(sound.pitch >= 0.8 && sound.pitch < 1.2 + 1e-9);
});

test("a creative player goes even when they can't pay, and the stone takes no damage", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(STONE, 1), creative: true });
  place(overworld, W, WAYSTONE, "Home", alex);
  _respond({ canceled: false, selection: 0 });
  await hold(alex);
  assert.deepEqual(alex.location, BESIDE_W);
  assert.equal(damageOf(alex.slots[0]), 0);
});

test("a player who can't pay is told on the action bar; the stone keeps its durability", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(STONE, 1), xp: 0 });
  place(overworld, W, WAYSTONE, "Home", alex);
  _respond({ canceled: false, selection: 0 });
  await hold(alex);
  assert.equal(alex.teleports.length, 0);
  assert.deepEqual(alex.actionbar.at(-1), error("chat.waystones.not_enough_xp"));
  assert.equal(damageOf(alex.slots[0]), 0);
});

test("the stone need not still be held at the choice (no warp hand); only a stone left in its slot wears", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(STONE, 1), xp: 30 });
  place(overworld, W, WAYSTONE, "Home", alex);
  use(alex);
  for (let i = 0; i < stones.use_time; i++) _runIntervals();
  const stone = alex.slots[0];
  alex.slots[0] = undefined; // moved away while the menu is open
  alex.slots[5] = stone;
  _respond({ canceled: false, selection: 0 });
  _flush();
  await settle();
  assert.deepEqual(alex.location, BESIDE_W);
  assert.equal(alex.actionbar.length, 0);
  assert.equal(damageOf(stone), 0);
});

test("a waystone whose block is gone says so; one that no longer exists does nothing", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(STONE, 1), xp: 30 });
  place(overworld, W, WAYSTONE, "Home", alex);
  use(alex);
  for (let i = 0; i < stones.use_time; i++) _runIntervals();
  overworld.set(W, "minecraft:stone");
  _respond({ canceled: false, selection: 0 });
  _flush();
  await settle();
  assert.equal(alex.teleports.length, 0);
  assert.deepEqual(alex.actionbar.at(-1), error("chat.waystones.waystone_missing"));
  place(overworld, W2, WAYSTONE, "Farm", alex);
  use(alex);
  for (let i = 0; i < stones.use_time; i++) _runIntervals();
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, W2), undefined);
  _respond({ canceled: false, selection: 0 });
  _flush();
  await settle();
  assert.equal(alex.teleports.length, 0);
  assert.equal(alex.actionbar.length, 1);
  assert.equal(damageOf(alex.slots[0]), 0);
});

test("switching away from the warp stone or taking damage stops its use", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(STONE, 1), xp: 30 });
  place(overworld, W, WAYSTONE, "Home", alex);
  use(alex);
  _runIntervals();
  alex.selectedSlotIndex = 1;
  for (let i = 0; i < stones.use_time; i++) _runIntervals();
  _flush();
  alex.selectedSlotIndex = 0;
  assert.equal(_shown.length, 0);
  use(alex);
  _runIntervals();
  _fire("after", "entityHurt", { hurtEntity: alex, damage: 1 });
  for (let i = 0; i < stones.use_time; i++) _runIntervals();
  _flush();
  assert.equal(_shown.length, 0);
  _respond({ canceled: false, selection: 0 });
  await hold(alex);
  assert.equal(alex.teleports.length, 1);
});

test("the warp stone's menu lists Return to Portal at the top while it stands", async () => {
  if (!table.warp_portals) return;
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(STONE, 1), xp: 30 });
  place(overworld, W, WAYSTONE, "Home", alex);
  const P = { x: 0, y: 64, z: 3 };
  const portal = table.warp_portals.blocks[0];
  overworld.set(P, portal, { [HALF]: "lower", "minecraft:cardinal_direction": "north" });
  overworld.set({ ...P, y: 65 }, portal, { [HALF]: "upper", "minecraft:cardinal_direction": "north" });
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, P), JSON.stringify({ uid: "portal1",
    type: table.warp_portals.type, dimension: overworld.id, pos: P, facing: "north", target: null, age: 0,
    name: { translate: table.messages.return_to_portal } }));
  alex.setDynamicProperty(table.warp_portals.return_property, "portal1");
  _respond({ canceled: false, selection: 0 });
  await hold(alex);
  const form = _shown.at(-1);
  assert.equal(form.buttons.length, 2);
  // Pinned first (WaystoneSelectionScreenBase#pinReturnPortalFirst L447-450).
  assert.deepEqual(form.buttons[0].text.rawtext[0], { translate: table.messages.return_to_portal });
  assert.equal(form.buttons[1].text.rawtext[0].text, "Home");
  assert.deepEqual(alex.location, { x: 0.5, y: 64.5, z: 2.5 });
  assert.equal(damageOf(alex.slots[0]), 1);
});

test("with enableDurability off the stone never wears", async () => {
  const saved = stones.durability;
  stones.durability = false;
  try {
    clearWorld();
    const overworld = makeDimension("minecraft:overworld");
    const alex = makePlayer(overworld, { held: worn(127), xp: 30 });
    place(overworld, W, WAYSTONE, "Home", alex);
    _respond({ canceled: false, selection: 0 });
    await hold(alex);
    assert.equal(alex.teleports.length, 1);
    assert.equal(damageOf(alex.slots[0]), 127);
  } finally {
    stones.durability = saved;
  }
});
