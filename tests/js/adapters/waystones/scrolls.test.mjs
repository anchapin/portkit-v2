// The fixed waystone runtime's warp, return and bound scrolls and the blank
// scroll (src/portkit/adapters/waystones/runtime), offline under node.
// Run: node --import ./tests/js/register.mjs --test tests/js/adapters/waystones/scrolls.test.mjs
// (tests/adapters/waystones/test_waystones.py runs it with PORTKIT_WAYSTONE_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../../../src/portkit/adapters/waystones/runtime/waystone_core.js";
import { registerWaystones } from "../../../../src/portkit/adapters/waystones/runtime/waystone.js";
import { _fire, _flush, _permutation, _runIntervals, _startup, world, GameMode, ItemStack } from "@minecraft/server";
import { _reset, _respond, _shown } from "@minecraft/server-ui";

const REQUIREMENTS = [
  { args: ["distance", 0.01], fn: "scaled_add_xp_cost", when: { is_interdimensional: false } },
  { args: [27], fn: "add_xp_cost", when: { is_interdimensional: true } },
  { args: [0], fn: "min_xp_cost", when: {} },
  { args: [27], fn: "max_xp_cost", when: {} },
];
const SCROLL_REQUIREMENTS = [...REQUIREMENTS.slice(0, 2), { args: [0.0], fn: "multiply_xp_cost", when: {} },
  ...REQUIREMENTS.slice(2)];
const BY_TYPE = {
  "waystones:waystone": SCROLL_REQUIREMENTS,
  "waystones:orange_sharestone": SCROLL_REQUIREMENTS,
  "waystones:warp_portal": SCROLL_REQUIREMENTS,
};

const FALLBACK = {
  block_types: { "waystones:waystone": "waystones:waystone", "waystones:orange_sharestone": "waystones:orange_sharestone" },
  blocks: ["waystones:orange_portstone", "waystones:orange_sharestone", "waystones:waystone"],
  component: "waystones:portkit_waystone",
  default_type: "waystones:waystone",
  half_state: "waystones:half",
  messages: {
    activated: "chat.waystones.waystone_activated",
    attunement_lost: "chat.waystones.warp_portal_attunement_lost",
    current_location: "gui.waystones.waystone_selection.current_location",
    missing: "chat.waystones.waystone_missing",
    no_space: "chat.waystones.warp_portal_no_space",
    none: "gui.waystones.waystone_selection.no_waystones_activated",
    none_shared: "gui.waystones.waystone_selection.no_sharestones_available",
    not_enough_xp: "chat.waystones.not_enough_xp",
    out_of_range: "chat.waystones.source_waystone_out_of_range",
    return_to_portal: "gui.waystones.waystone_selection.return_to_portal",
    source_item_missing: "chat.waystones.source_item_missing",
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
  portstones: { "waystones:orange_portstone": { requirements: REQUIREMENTS, target: "waystones:orange_sharestone",
    title: "container.waystones.orange_portstone" } },
  range_sq: 64,
  restricted_origins: ["PLAYER"],
  rune_blocks: [],
  rune_state: "waystones:runes",
  scrolls: {
    binding_property: "waystones:portkit_bound_waystone",
    blank: ["waystones:blank_scroll"],
    bound: "waystones:bound_scroll",
    error_style: "\u00a74",
    items: {
      "waystones:bound_scroll": { kind: "bound", requirements: BY_TYPE },
      "waystones:return_scroll": { kind: "return", requirements: BY_TYPE },
      "waystones:warp_scroll": { kind: "warp", requirements: BY_TYPE },
    },
    name_style: "\u00a7b",
    network: "waystones:waystone",
    title: "container.waystones.waystone_selection",
    use_time: 32,
  },
  sounds: {
    activate: { id: "random.levelup", pitch: 1.0, volume: 0.2 },
    arrive: { id: "portal.travel", pitch: 1.0, volume: 0.05 },
    depart: { id: "portal.travel", pitch: 1.0, volume: 0.01 },
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
      requirements: SCROLL_REQUIREMENTS,
      title: "container.waystones.waystone_selection",
      use_time: 32,
    },
    type: "waystones:warp_portal",
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_WAYSTONE_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerWaystones(table);
const scrolls = table.scrolls;
const registered = _startup();
const waystoneComponent = registered[table.component];
const kindOf = (kind) => Object.keys(scrolls.items).find((id) => scrolls.items[id].kind === kind);
const WARP = kindOf("warp");
const RETURN = kindOf("return");
const BOUND = kindOf("bound");
const BLANK = scrolls.blank[0];
const HALF = table.half_state;
const typeBlock = (type) => Object.keys(table.block_types).find((id) => table.block_types[id] === type);
const WAYSTONE = typeBlock(scrolls.network);
const SHARESTONE = Object.keys(table.block_types).find((id) => table.networks[table.block_types[id]].shared);
const PORTSTONE = Object.keys(table.portstones)[0];
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

async function hold(player, ticks = scrolls.use_time) {
  use(player);
  for (let i = 0; i < ticks; i++) _runIntervals();
  _flush();
  await settle();
}

function interact(dimension, pos, player) {
  waystoneComponent.onPlayerInteract({ block: dimension.blockAt(pos), dimension, player });
  _flush();
}

const W = { x: 100, y: 64, z: 0 };
const W2 = { x: 20, y: 64, z: 0 };
const S = { x: -40, y: 64, z: 0 };
const BESIDE_W = { x: 100.5, y: 64.5, z: -0.5 };
const error = (key) => ({ rawtext: [{ text: "\u00a74" }, { translate: key }] });

// -- core ----------------------------------------------------------------------

test("the nearest activated waystone in the player's dimension; the first of equals", () => {
  const records = [
    { uid: "a", type: "waystones:waystone", dimension: "minecraft:overworld", pos: { x: 10, y: 64, z: 0 } },
    { uid: "b", type: "waystones:waystone", dimension: "minecraft:overworld", pos: { x: -10, y: 64, z: 0 } },
    { uid: "c", type: "waystones:waystone", dimension: "minecraft:the_nether", pos: { x: 0, y: 64, z: 0 } },
    { uid: "d", type: "waystones:orange_sharestone", dimension: "minecraft:overworld", pos: { x: 1, y: 64, z: 0 } },
  ];
  const at = { x: 0.5, y: 64.5, z: 0.5 };
  const near = (activated) => core.nearestWaystone(activated, records, "waystones:waystone", "minecraft:overworld",
    at, "waystones:waystone");
  assert.equal(near(["a", "b", "c", "d"]).uid, "a");
  assert.equal(near(["b", "a"]).uid, "b");
  assert.equal(near(["c", "d", "gone"]), undefined);
});

test("binding goes ahead with a free slot or the last blank scroll outside creative", () => {
  assert.equal(core.mayBind(1, false, false, 5), true);
  assert.equal(core.mayBind(0, false, false, 1), true);
  assert.equal(core.mayBind(0, false, true, 1), false);
  assert.equal(core.mayBind(0, false, false, 2), false);
  assert.equal(core.mayBind(0, true, true, 2), true);
});

// -- the warp scroll ---------------------------------------------------------------

test("a warp scroll held for its use time opens the activated waystones; a choice teleports and uses it up", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(WARP, 2) });
  place(overworld, W, WAYSTONE, "Home", alex);
  use(alex);
  assert.deepEqual(overworld.sounds.at(-1), { id: "portal.trigger", location: alex.location, volume: 0.1, pitch: 2.0 });
  for (let i = 0; i < scrolls.use_time - 1; i++) _runIntervals();
  _flush();
  assert.equal(_shown.length, 0);
  _runIntervals();
  _respond({ canceled: false, selection: 0 });
  _flush();
  await settle();
  const form = _shown.at(-1);
  assert.deepEqual(form.title, { translate: "container.waystones.waystone_selection" });
  assert.equal(form.body, ""); // no waystone in use: no "Current Location"
  assert.deepEqual(form.buttons.map((b) => b.text.rawtext), [[{ text: "Home" }]]); // free: no cost line
  assert.deepEqual(alex.location, BESIDE_W);
  assert.equal(alex.slots[0].amount, 1);
  assert.equal(alex.xp, 0);
});

test("a warp scroll no longer in hand at the choice says so; a creative player keeps it", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(WARP, 1) });
  place(overworld, W, WAYSTONE, "Home", alex);
  use(alex);
  for (let i = 0; i < scrolls.use_time; i++) _runIntervals();
  alex.slots[0] = undefined; // dropped while the menu is open
  _respond({ canceled: false, selection: 0 });
  _flush();
  await settle();
  assert.equal(alex.teleports.length, 0);
  assert.deepEqual(alex.actionbar.at(-1), error("chat.waystones.source_item_missing"));
  const steve = makePlayer(overworld, { held: new ItemStack(WARP, 1), creative: true });
  place(overworld, W2, WAYSTONE, "Farm", steve);
  _respond({ canceled: false, selection: 0 });
  await hold(steve);
  assert.equal(steve.teleports.length, 1);
  assert.equal(steve.slots[0].amount, 1);
});

test("switching away from a scroll or taking damage stops its use", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(RETURN, 1) });
  place(overworld, W, WAYSTONE, "Home", alex);
  use(alex);
  _runIntervals();
  alex.selectedSlotIndex = 1;
  for (let i = 0; i < scrolls.use_time; i++) _runIntervals();
  alex.selectedSlotIndex = 0;
  assert.equal(alex.teleports.length, 0);
  use(alex);
  _runIntervals();
  _fire("after", "entityHurt", { hurtEntity: alex, damage: 1 });
  for (let i = 0; i < scrolls.use_time; i++) _runIntervals();
  assert.equal(alex.teleports.length, 0);
  await hold(alex);
  assert.equal(alex.teleports.length, 1);
});

// -- the return scroll -------------------------------------------------------------

test("a return scroll goes to the nearest activated waystone in the player's dimension", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const nether = makeDimension("minecraft:the_nether");
  const alex = makePlayer(overworld, { held: new ItemStack(RETURN, 3), location: { x: 90.5, y: 64, z: 0.5 } });
  place(nether, { x: 91, y: 64, z: 0 }, WAYSTONE, "Nether", alex);
  place(overworld, W2, WAYSTONE, "Farm", alex);
  place(overworld, W, WAYSTONE, "Home", alex);
  await hold(alex);
  assert.deepEqual(alex.location, BESIDE_W);
  assert.equal(alex.slots[0].amount, 2);
  assert.equal(_shown.length, 0); // no menu
});

test("a return scroll with no activated waystone in the dimension does nothing", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const nether = makeDimension("minecraft:the_nether");
  const alex = makePlayer(overworld, { held: new ItemStack(RETURN, 1) });
  place(nether, W, WAYSTONE, "Nether", alex);
  place(overworld, W2, WAYSTONE, "Not mine");
  await hold(alex);
  assert.equal(alex.teleports.length, 0);
  assert.equal(alex.slots[0].amount, 1);
  assert.equal(alex.actionbar.length, 0);
});

test("a return scroll goes to the return portal while it stands", async () => {
  if (!table.warp_portals) return;
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(RETURN, 1), xp: 50 });
  place(overworld, W2, WAYSTONE, "Farm", alex);
  const P = { x: 0, y: 64, z: 3 };
  const portal = table.warp_portals.blocks[0];
  overworld.set(P, portal, { [HALF]: "lower", "minecraft:cardinal_direction": "north" });
  overworld.set({ ...P, y: 65 }, portal, { [HALF]: "upper", "minecraft:cardinal_direction": "north" });
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, P), JSON.stringify({ uid: "portal1",
    type: table.warp_portals.type, dimension: overworld.id, pos: P, facing: "north", target: null, age: 0,
    name: { translate: table.messages.return_to_portal } }));
  alex.setDynamicProperty(table.warp_portals.return_property, "portal1");
  await hold(alex);
  assert.deepEqual(alex.location, { x: 0.5, y: 64.5, z: 2.5 });
  assert.equal(alex.slots[0], undefined);
});

// -- the blank and bound scrolls -------------------------------------------------

test("a blank scroll on a waystone (either half) gives a bound scroll with its name; the waystone isn't used", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(BLANK, 3) });
  const uid = place(overworld, W, WAYSTONE, "Home");
  interact(overworld, { ...W, y: 65 }, alex);
  assert.equal(alex.slots[0].amount, 2);
  const bound = alex.slots[1];
  assert.equal(bound.typeId, BOUND);
  assert.equal(bound.getDynamicProperty(scrolls.binding_property), uid);
  assert.deepEqual(bound.getLore(), ["\u00a7bHome"]);
  // Not activated, no menu, no message.
  assert.equal(alex.getDynamicProperty(core.activatedKey("waystones")), undefined);
  assert.equal(_shown.length, 0);
  assert.equal(alex.chat.length, 0);
  // Sneaking binds too (the item's useOn runs either way).
  alex.isSneaking = true;
  interact(overworld, W, alex);
  assert.equal(alex.slots[2].typeId, BOUND);
  assert.equal(_shown.length, 0);
});

test("a full inventory binds only the last blank scroll; creative keeps it and needs a free slot", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  place(overworld, W, WAYSTONE, "");
  const full = makePlayer(overworld, { held: new ItemStack(BLANK, 2), free: 0 });
  interact(overworld, W, full);
  assert.equal(full.slots[0].amount, 2);
  const last = makePlayer(overworld, { held: new ItemStack(BLANK, 1), free: 0 });
  interact(overworld, W, last);
  assert.equal(last.slots[0].typeId, BOUND);
  assert.deepEqual(last.slots[0].getLore(), []); // an unnamed waystone: no lore
  const creative = makePlayer(overworld, { held: new ItemStack(BLANK, 1), free: 0, creative: true });
  interact(overworld, W, creative);
  assert.equal(creative.slots[0].typeId, BLANK);
  const roomy = makePlayer(overworld, { held: new ItemStack(BLANK, 1), creative: true });
  interact(overworld, W, roomy);
  assert.equal(roomy.slots[0].amount, 1);
  assert.equal(roomy.slots[1].typeId, BOUND);
});

test("a blank scroll binds a sharestone, and does nothing on a portstone", () => {
  if (!SHARESTONE || !PORTSTONE) return;
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(BLANK, 2) });
  const uid = place(overworld, S, SHARESTONE, "Market");
  interact(overworld, S, alex);
  assert.equal(alex.slots[1].getDynamicProperty(scrolls.binding_property), uid);
  const P = { x: -60, y: 64, z: 0 };
  overworld.set(P, PORTSTONE, { [HALF]: "lower", "minecraft:cardinal_direction": "north" });
  interact(overworld, P, alex);
  assert.equal(alex.slots[0].amount, 1);
  assert.equal(_shown.length, 0);
});

test("a bound scroll goes to its waystone (any dimension), even one the player never activated", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const nether = makeDimension("minecraft:the_nether");
  const binder = makePlayer(overworld, { held: new ItemStack(BLANK, 1) });
  place(overworld, W, WAYSTONE, "Home");
  interact(overworld, W, binder);
  const alex = makePlayer(nether, { held: binder.slots[0], xp: 0 });
  await hold(alex);
  assert.deepEqual(alex.location, BESIDE_W);
  assert.equal(alex.dimension, overworld);
  assert.equal(alex.slots[0], undefined);
  assert.equal(_shown.length, 0);
});

test("a bound scroll whose waystone is gone does nothing; whose block is gone says so; unbound does nothing", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const binder = makePlayer(overworld, { held: new ItemStack(BLANK, 1) });
  place(overworld, W, WAYSTONE, "Home");
  interact(overworld, W, binder);
  const scroll = binder.slots[0];
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, W), undefined);
  const alex = makePlayer(overworld, { held: scroll });
  await hold(alex);
  assert.equal(alex.teleports.length, 0);
  assert.equal(alex.actionbar.length, 0);
  assert.equal(alex.slots[0], scroll);
  // The record stands but its block was swapped away.
  const binder2 = makePlayer(overworld, { held: new ItemStack(BLANK, 1) });
  place(overworld, W2, WAYSTONE, "Farm");
  interact(overworld, W2, binder2);
  overworld.set(W2, "minecraft:stone");
  const steve = makePlayer(overworld, { held: binder2.slots[0] });
  await hold(steve);
  assert.equal(steve.teleports.length, 0);
  assert.deepEqual(steve.actionbar.at(-1), error("chat.waystones.waystone_missing"));
  const blank = makePlayer(overworld, { held: new ItemStack(BOUND, 1) });
  await hold(blank);
  assert.equal(blank.teleports.length, 0);
  assert.equal(blank.actionbar.length, 0);
});

test("a player who can't pay a scroll teleport is told and keeps the scroll", async () => {
  // At the defaults scroll teleports are free (source_is_scroll multiplies by
  // 0); with the multiplier gone the distance cost applies.
  const rules = scrolls.items[RETURN].requirements;
  const saved = rules[scrolls.network];
  rules[scrolls.network] = saved.filter((r) => r.fn !== "multiply_xp_cost");
  try {
    clearWorld();
    const overworld = makeDimension("minecraft:overworld");
    const alex = makePlayer(overworld, { held: new ItemStack(RETURN, 1), xp: 0 });
    place(overworld, W, WAYSTONE, "Home", alex);
    await hold(alex);
    assert.equal(alex.teleports.length, 0);
    assert.deepEqual(alex.actionbar.at(-1), error("chat.waystones.not_enough_xp"));
    assert.equal(alex.slots[0].amount, 1);
    alex.xp = 5;
    await hold(alex);
    assert.equal(alex.teleports.length, 1);
    assert.equal(alex.xp, 5 - core.cost(rules[scrolls.network], { is_interdimensional: false,
      distance: core.distance({ x: 0.5, y: 64, z: 0.5 }, W) }));
  } finally {
    rules[scrolls.network] = saved;
  }
});
