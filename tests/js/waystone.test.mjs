// The fixed waystone runtime (src/portkit/runtime), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/waystone.test.mjs
// (tests/test_waystones.py runs it with PORTKIT_WAYSTONE_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../src/portkit/runtime/waystone_core.js";
import { registerWaystones } from "../../src/portkit/runtime/waystone.js";
import { _fire, _flush, _permutation, _startup, world, GameMode } from "@minecraft/server";
import { _reset, _respond, _shown } from "@minecraft/server-ui";

const REQUIREMENTS = [
  { args: ["distance", 0.01], fn: "scaled_add_xp_cost", when: { is_interdimensional: false } },
  { args: [27], fn: "add_xp_cost", when: { is_interdimensional: true } },
  { args: [0], fn: "min_xp_cost", when: {} },
  { args: [27], fn: "max_xp_cost", when: {} },
];

const FALLBACK = {
  block_types: {
    "waystones:mossy_waystone": "waystones:waystone",
    "waystones:orange_sharestone": "waystones:orange_sharestone",
    "waystones:waystone": "waystones:waystone",
  },
  blocks: ["waystones:mossy_waystone", "waystones:orange_sharestone", "waystones:waystone"],
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
    only_owner: "chat.waystones.only_owner_can_edit",
    out_of_range: "chat.waystones.source_waystone_out_of_range",
    save: "gui.waystones.waystone_settings.save",
    settings: "container.waystones.waystone_settings",
    sharestone_name: "container.waystones.sharestone",
    title: "container.waystones.waystone_selection",
    unnamed: "gui.waystones.waystone_selection.unnamed_waystone",
    untitled: "waystones.untitled_waystone",
    waystone_name: "container.waystones.waystone",
    xp_cost: "gui.waystones.waystone_selection.xp_requirement",
  },
  name_max_length: 128,
  namespace: "waystones",
  networks: {
    "waystones:orange_sharestone": { name: "sharestone_name", none: "none_shared", requirements: REQUIREMENTS, shared: true },
    "waystones:waystone": { name: "waystone_name", none: "none", requirements: REQUIREMENTS, shared: false },
  },
  range_sq: 64,
  restricted_origins: ["PLAYER"],
  sounds: {
    activate: { id: "random.levelup", pitch: 1.0, volume: 0.2 },
    arrive: { id: "portal.travel", pitch: 1.0, volume: 0.05 },
    depart: { id: "portal.travel", pitch: 1.0, volume: 0.01 },
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_WAYSTONE_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerWaystones(table);
const component = _startup()[table.component];
const HALF = table.half_state;
const TYPE = "waystones:waystone";
const ORANGE = "waystones:orange_sharestone";

// -- a tiny world --------------------------------------------------------------

function makeDimension(id) {
  const blocks = new Map();
  const dimension = {
    id,
    sounds: [],
    commands: [],
    unloaded: false,
    key: (p) => `${p.x},${p.y},${p.z}`,
    getBlock(location) {
      if (dimension.unloaded) throw new Error("LocationInUnloadedChunkError");
      return blockAt(location);
    },
    runCommand(command) {
      dimension.commands.push(command);
      const m = command.match(/^setblock (-?\d+) (-?\d+) (-?\d+) air destroy$/);
      if (m) blocks.delete(`${m[1]},${m[2]},${m[3]}`);
      return { successCount: 1 };
    },
    playSound(soundId, location, options) { dimension.sounds.push({ id: soundId, location, ...options }); },
    set(location, typeId, states) { blocks.set(dimension.key(location), _permutation(typeId, states)); },
    typeAt(location) { const p = blocks.get(dimension.key(location)); return p ? p.type.id : "minecraft:air"; },
  };
  function blockAt(location) {
    const loc = { x: location.x, y: location.y, z: location.z };
    const block = {
      dimension,
      location: loc,
      get permutation() { return blocks.get(dimension.key(loc)) ?? _permutation("minecraft:air"); },
      get typeId() { return this.permutation.type.id; },
      get isAir() { return this.typeId === "minecraft:air"; },
      get isLiquid() { return this.typeId === "minecraft:water"; },
      above: (n = 1) => blockAt({ ...loc, y: loc.y + n }),
      below: (n = 1) => blockAt({ ...loc, y: loc.y - n }),
      setPermutation(p) { blocks.set(dimension.key(loc), p); },
      setType(t) { if (t === "minecraft:air") blocks.delete(dimension.key(loc)); else blocks.set(dimension.key(loc), _permutation(t)); },
    };
    return block;
  }
  dimension.blockAt = blockAt;
  world._dimensions.set(id, dimension);
  return dimension;
}

function makePlayer(dimension, { id = "-1", name = "Alex", xp = 0, creative = false, location } = {}) {
  const props = new Map();
  const player = {
    id,
    name,
    dimension,
    location: location ?? { x: 0, y: 64, z: 0 },
    isSneaking: false,
    xp,
    actionbar: [],
    messages: [],
    teleports: [],
    getTotalXp() { return this.xp; },
    addExperience(n) { this.xp += n; return this.xp; },
    getGameMode: () => (creative ? GameMode.Creative : GameMode.Survival),
    getDynamicProperty: (k) => props.get(k),
    setDynamicProperty: (k, v) => (v === undefined ? props.delete(k) : props.set(k, v)),
    getRotation: () => ({ x: 12, y: 0 }),
    sendMessage(m) { this.messages.push(m); },
    onScreenDisplay: { setActionBar: (m) => player.actionbar.push(m) },
    teleport(location, options) {
      this.teleports.push({ location, ...options });
      this.location = location;
      if (options && options.dimension) this.dimension = options.dimension;
    },
  };
  return player;
}

function clearWorld() {
  for (const key of world.getDynamicPropertyIds()) world.setDynamicProperty(key, undefined);
  _reset();
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

async function place(dimension, player, location, facing = "north", typeId = TYPE) {
  const at = dimension.blockAt(location);
  const before = { block: at, player, cancel: false };
  component.beforeOnPlayerPlace(before);
  if (before.cancel) return false;
  dimension.set(location, typeId, { "minecraft:cardinal_direction": facing, [HALF]: "lower" });
  _fire("after", "playerPlaceBlock", { block: dimension.blockAt(location), player, dimension });
  _flush();
  await tick();
  return true;
}

function use(dimension, player, location) {
  component.onPlayerInteract({ block: dimension.blockAt(location), dimension, player });
}

// -- core ----------------------------------------------------------------------

test("cost follows the warpRequirements default", () => {
  const r = REQUIREMENTS;
  assert.equal(core.cost(r, { is_interdimensional: false, distance: 99.9 }), 0);
  assert.equal(core.cost(r, { is_interdimensional: false, distance: 1500.7 }), 15);
  assert.equal(core.cost(r, { is_interdimensional: false, distance: 99999 }), 27);
  assert.equal(core.cost(r, { is_interdimensional: true, distance: 10 }), 27);
  assert.equal(core.cost([], { is_interdimensional: true, distance: 10 }), 0);
  assert.equal(core.cost([{ fn: "multiply_xp_cost", args: [0], when: {} }, ...r], { is_interdimensional: false, distance: 500 }), 5);
});

test("affording: total points, creative always", () => {
  assert.equal(core.canAfford(10, 15, false), false);
  assert.equal(core.canAfford(15, 15, false), true);
  assert.equal(core.canAfford(0, 27, true), true);
  assert.equal(core.canAfford(0, 0, false), true);
});

test("destination: facing first, then east, west, south, north; else the waystone itself", () => {
  assert.equal(core.offsetDirection("north", () => true), "north");
  assert.equal(core.offsetDirection("north", (d) => d === "west"), "west");
  assert.equal(core.offsetDirection("south", () => false), null);
  assert.deepEqual(core.destination({ x: 10, y: 64, z: -3 }, "east", "north"),
    { location: { x: 11.5, y: 64.5, z: -2.5 }, yaw: -90 });
  assert.deepEqual(core.destination({ x: 0, y: 5, z: 0 }, null, "south"), { location: { x: 0.5, y: 5.5, z: 0.5 }, yaw: 0 });
  assert.equal(core.destination({ x: 0, y: 5, z: 0 }, "north", "north").yaw, -180);
});

test("names: blank is untitled, long is cut; empty shows as unnamed in lists", () => {
  assert.deepEqual(core.legalName("   ", 128, "waystones.untitled_waystone"), { translate: "waystones.untitled_waystone" });
  assert.deepEqual(core.legalName("x".repeat(200), 128, "u"), { text: "x".repeat(128) });
  assert.deepEqual(core.nameText({ text: "" }, "unnamed"), { translate: "unnamed" });
  assert.deepEqual(core.nameText({ text: "" }), { text: "" });
  assert.deepEqual(core.nameText({ translate: "k" }, "unnamed"), { translate: "k" });
});

test("edit permission: owner only for owned waystones", () => {
  assert.equal(core.editError({ owner: "1", origin: "PLAYER" }, "1", ["PLAYER"]), null);
  assert.equal(core.editError({ owner: "1", origin: "PLAYER" }, "2", ["PLAYER"]), "only_owner");
  assert.equal(core.editError({ owner: null, origin: "UNKNOWN" }, "2", ["PLAYER"]), null);
  assert.equal(core.editError({ owner: null, origin: "VILLAGE" }, "2", ["PLAYER", "VILLAGE"]), "only_owner");
});

test("menu entries: activation order, existing only, without the one in use", () => {
  const records = [{ uid: "a" }, { uid: "b" }, { uid: "c" }];
  assert.deepEqual(core.targets(["c", "a", "x", "b", "c"], records, "b").map((r) => r.uid), ["c", "a"]);
});

// -- binding -------------------------------------------------------------------

test("placing sets the upper half, owns, activates and asks for a name", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "7" });
  _respond({ canceled: false, formValues: ["Home"] });
  assert.equal(await place(overworld, alex, { x: 0, y: 64, z: 0 }, "east"), true);
  const upper = overworld.blockAt({ x: 0, y: 65, z: 0 }).permutation;
  assert.equal(upper.getState(HALF), "upper");
  assert.equal(upper.getState("minecraft:cardinal_direction"), "east");
  const record = JSON.parse(world.getDynamicProperty(core.recordKey("waystones", "minecraft:overworld", { x: 0, y: 64, z: 0 })));
  assert.equal(record.owner, "7");
  assert.equal(record.origin, "PLAYER");
  assert.equal(record.facing, "east");
  assert.deepEqual(record.name, { text: "Home" });
  assert.deepEqual(JSON.parse(alex.getDynamicProperty(core.activatedKey("waystones"))), [record.uid]);
  assert.equal(_shown[0].kind, "modal");
});

test("no room above: the placement is cancelled", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  overworld.set({ x: 0, y: 65, z: 0 }, "minecraft:stone");
  assert.equal(await place(overworld, makePlayer(overworld), { x: 0, y: 64, z: 0 }), false);
});

test("using an unknown waystone activates it with the message and the level-up sound", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  const sam = makePlayer(overworld, { id: "2", name: "Sam" });
  _respond({ canceled: false, formValues: ["Spawn"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  use(overworld, sam, { x: 0, y: 65, z: 0 });
  assert.equal(sam.messages.length, 1);
  assert.equal(sam.messages[0].rawtext[0].translate, table.messages.activated);
  assert.deepEqual(sam.messages[0].rawtext[0].with.rawtext, [{ text: "Spawn" }]);
  assert.equal(overworld.sounds.at(-1).id, table.sounds.activate.id);
  assert.equal(overworld.sounds.at(-1).volume, table.sounds.activate.volume);
});

test("using an activated waystone opens the menu; choosing teleports and charges experience", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1", xp: 100 });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  alex.location = { x: 1500, y: 64, z: 0 };
  _respond({ canceled: false, formValues: ["B"] });
  await place(overworld, alex, { x: 1500, y: 64, z: 2 }, "south");
  _respond({ canceled: false, selection: 0 });
  use(overworld, alex, { x: 1500, y: 64, z: 2 });
  _flush();
  await tick();
  const menu = _shown.at(-1);
  assert.equal(menu.kind, "action");
  assert.equal(menu.title.translate, table.messages.title);
  assert.equal(menu.buttons.length, 1);
  assert.deepEqual(menu.buttons[0].text.rawtext[0], { text: "A" });
  assert.equal(menu.buttons[0].text.rawtext[2].rawtext[0].with.rawtext[0].text, "14");
  const hop = alex.teleports.at(-1);
  // Facing north is free: the block north of the waystone, turned north.
  assert.deepEqual(hop.location, { x: 0.5, y: 64.5, z: -0.5 });
  assert.equal(hop.rotation.y, -180);
  assert.equal(hop.rotation.x, 12);
  assert.equal(alex.xp, 86);
  assert.deepEqual(overworld.sounds.slice(-2).map((s) => s.volume), [0.01, 0.05]);
});

test("not enough experience: no teleport, the action bar says so; creative goes anyway", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const nether = makeDimension("minecraft:nether");
  const alex = makePlayer(overworld, { id: "1", xp: 5 });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  alex.dimension = nether;
  _respond({ canceled: false, formValues: ["N"] });
  await place(nether, alex, { x: 0, y: 64, z: 0 });
  _respond({ canceled: false, selection: 0 });
  use(nether, alex, { x: 0, y: 64, z: 0 });
  _flush();
  await tick();
  assert.equal(alex.teleports.length, 0);
  assert.equal(alex.actionbar.at(-1).rawtext[0].translate, table.messages.not_enough_xp);

  const creative = makePlayer(nether, { id: "1", xp: 0, creative: true });
  creative.setDynamicProperty(core.activatedKey("waystones"), alex.getDynamicProperty(core.activatedKey("waystones")));
  _respond({ canceled: false, selection: 0 });
  use(nether, creative, { x: 0, y: 64, z: 0 });
  _flush();
  await tick();
  assert.equal(creative.teleports.length, 1);
  assert.equal(creative.teleports[0].dimension, overworld);
  assert.equal(creative.xp, -27);
});

test("no free side: the player lands on the waystone's own block", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1", xp: 0 });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) overworld.set({ x: dx, y: 64, z: dz }, "minecraft:stone");
  _respond({ canceled: false, formValues: ["B"] });
  await place(overworld, alex, { x: 5, y: 64, z: 0 });
  _respond({ canceled: false, selection: 0 });
  use(overworld, alex, { x: 5, y: 64, z: 0 });
  _flush();
  await tick();
  assert.deepEqual(alex.teleports.at(-1).location, { x: 0.5, y: 64.5, z: 0.5 });
});

test("too far from the waystone used: no teleport", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  _respond({ canceled: false, formValues: ["B"] });
  await place(overworld, alex, { x: 50, y: 64, z: 0 });
  alex.location = { x: 0, y: 64, z: 0 };
  _respond({ canceled: false, selection: 0 });
  use(overworld, alex, { x: 50, y: 64, z: 0 });
  _flush();
  await tick();
  assert.equal(alex.teleports.length, 0);
  assert.equal(alex.actionbar.at(-1).rawtext[0].translate, table.messages.out_of_range);
});

test("sneaking: the owner renames, anyone else is told only the owner may", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  const sam = makePlayer(overworld, { id: "2" });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  sam.isSneaking = true;
  use(overworld, sam, { x: 0, y: 64, z: 0 });
  assert.equal(sam.actionbar.at(-1).rawtext[0].translate, table.messages.only_owner);
  alex.isSneaking = true;
  _respond({ canceled: false, formValues: [" "] });
  use(overworld, alex, { x: 0, y: 64, z: 0 });
  _flush();
  await tick();
  const record = JSON.parse(world.getDynamicProperty(core.recordKey("waystones", "minecraft:overworld", { x: 0, y: 64, z: 0 })));
  assert.deepEqual(record.name, { translate: table.messages.untitled });
});

test("breaking the upper half destroys the lower one with its drops and forgets the waystone", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  const upperPos = { x: 0, y: 65, z: 0 };
  const permutation = overworld.blockAt(upperPos).permutation;
  overworld.blockAt(upperPos).setType("minecraft:air");
  component.onPlayerBreak({ block: overworld.blockAt(upperPos), brokenBlockPermutation: permutation, dimension: overworld, player: alex });
  assert.deepEqual(overworld.commands, ["setblock 0 64 0 air destroy"]);
  assert.equal(world.getDynamicProperty(core.recordKey("waystones", "minecraft:overworld", { x: 0, y: 64, z: 0 })), undefined);
});

test("breaking the lower half removes the upper one without drops", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  const lowerPos = { x: 0, y: 64, z: 0 };
  const permutation = overworld.blockAt(lowerPos).permutation;
  overworld.blockAt(lowerPos).setType("minecraft:air");
  component.onPlayerBreak({ block: overworld.blockAt(lowerPos), brokenBlockPermutation: permutation, dimension: overworld, player: alex });
  assert.deepEqual(overworld.commands, []);
  assert.equal(overworld.typeAt({ x: 0, y: 65, z: 0 }), "minecraft:air");
});

test("a target whose block is gone is forgotten and reported missing", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  _respond({ canceled: false, formValues: ["B"] });
  await place(overworld, alex, { x: 5, y: 64, z: 0 });
  overworld.blockAt({ x: 0, y: 64, z: 0 }).setType("minecraft:air");
  _respond({ canceled: false, selection: 0 });
  use(overworld, alex, { x: 5, y: 64, z: 0 });
  _flush();
  await tick();
  assert.equal(alex.teleports.length, 0);
  assert.equal(alex.actionbar.at(-1).rawtext[0].translate, table.messages.missing);
  assert.equal(world.getDynamicProperty(core.recordKey("waystones", "minecraft:overworld", { x: 0, y: 64, z: 0 })), undefined);
});

test("an unloaded target: the player lands on its front", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 }, "west");
  _respond({ canceled: false, formValues: ["B"] });
  await place(overworld, alex, { x: 5, y: 64, z: 0 });
  overworld.unloaded = true;
  _respond({ canceled: false, selection: 0 });
  use(overworld, alex, { x: 5, y: 64, z: 0 });
  _flush();
  await tick();
  assert.deepEqual(alex.teleports.at(-1).location, { x: -0.5, y: 64.5, z: 0.5 });
});

// -- sharestones ---------------------------------------------------------------

test("shared targets: same type only, without the one in use, in placement order", () => {
  const records = [
    { uid: "b", type: ORANGE, order: 2 },
    { uid: "w", order: 0 },
    { uid: "a", type: ORANGE, order: 1 },
    { uid: "r", type: "waystones:red_sharestone", order: 3 },
    { uid: "c", type: ORANGE, order: 2 },
  ];
  assert.deepEqual(core.sharedTargets(records, ORANGE, "a", TYPE).map((r) => r.uid), ["b", "c"]);
  assert.deepEqual(core.sharedTargets(records, TYPE, "x", TYPE).map((r) => r.uid), ["w"]);
  assert.equal(core.recordType({}, TYPE), TYPE);
});

test("placing a sharestone owns it and asks for its name, but activates nothing", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "7" });
  _respond({ canceled: false, formValues: ["Market"] });
  assert.equal(await place(overworld, alex, { x: 0, y: 64, z: 0 }, "east", ORANGE), true);
  assert.equal(overworld.blockAt({ x: 0, y: 65, z: 0 }).permutation.getState(HALF), "upper");
  const record = JSON.parse(world.getDynamicProperty(core.recordKey("waystones", "minecraft:overworld", { x: 0, y: 64, z: 0 })));
  assert.equal(record.type, ORANGE);
  assert.equal(record.owner, "7");
  assert.deepEqual(record.name, { text: "Market" });
  assert.equal(alex.getDynamicProperty(core.activatedKey("waystones")), undefined);
  // "Edit %s" with the block entity's name (Sharestone), as Java's settings title.
  assert.deepEqual(_shown[0].title.rawtext[0].with.rawtext, [{ translate: table.messages.sharestone_name }]);
});

test("using a sharestone opens its colour's network at once; choosing teleports and charges", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const nether = makeDimension("minecraft:nether");
  const alex = makePlayer(overworld, { id: "1" });
  const sam = makePlayer(overworld, { id: "2", name: "Sam", xp: 100 });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 }, "north", ORANGE);
  _respond({ canceled: false, formValues: ["W"] });
  await place(overworld, alex, { x: 20, y: 64, z: 0 });
  alex.dimension = nether;
  _respond({ canceled: false, formValues: ["N"] });
  await place(nether, alex, { x: 0, y: 64, z: 0 }, "north", ORANGE);
  alex.dimension = overworld;
  alex.location = { x: 1000, y: 64, z: 0 };
  _respond({ canceled: false, formValues: ["B"] });
  await place(overworld, alex, { x: 1000, y: 64, z: 2 }, "south", ORANGE);
  // Sam never touched any of them: no activation, no chat, the menu opens.
  sam.location = { x: 1000, y: 64, z: 0 };
  _respond({ canceled: false, selection: 0 });
  use(overworld, sam, { x: 1000, y: 65, z: 2 });
  _flush();
  await tick();
  assert.equal(sam.messages.length, 0);
  assert.equal(sam.getDynamicProperty(core.activatedKey("waystones")), undefined);
  const menu = _shown.at(-1);
  assert.equal(menu.kind, "action");
  // Every other orange sharestone, in placement order; never the waystone.
  assert.deepEqual(menu.buttons.map((b) => b.text.rawtext[0]), [{ text: "A" }, { text: "N" }]);
  assert.equal(menu.buttons[0].text.rawtext[2].rawtext[0].with.rawtext[0].text, "9");
  assert.equal(menu.buttons[1].text.rawtext[2].rawtext[0].with.rawtext[0].text, "27");
  assert.deepEqual(sam.teleports.at(-1).location, { x: 0.5, y: 64.5, z: -0.5 });
  assert.equal(sam.xp, 91);
});

test("a lone sharestone says there are no matching sharestones", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 }, "north", ORANGE);
  _respond({ canceled: true });
  use(overworld, alex, { x: 0, y: 64, z: 0 });
  _flush();
  await tick();
  const menu = _shown.at(-1);
  assert.equal(menu.buttons.length, 0);
  assert.equal(menu.body.rawtext.at(-1).rawtext[0].translate, table.messages.none_shared);
});

test("a sharestone whose block became a waystone is no longer a sharestone target", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 }, "north", ORANGE);
  _respond({ canceled: false, formValues: ["B"] });
  await place(overworld, alex, { x: 5, y: 64, z: 0 }, "north", ORANGE);
  overworld.set({ x: 0, y: 64, z: 0 }, TYPE, { "minecraft:cardinal_direction": "north", [HALF]: "lower" });
  _respond({ canceled: false, selection: 0 });
  use(overworld, alex, { x: 5, y: 64, z: 0 });
  _flush();
  await tick();
  assert.equal(alex.teleports.length, 0);
  assert.equal(alex.actionbar.at(-1).rawtext[0].translate, table.messages.missing);
});

test("the waystone settings title is Edit Waystone, as Java's", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  _respond({ canceled: false, formValues: ["Home"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  assert.deepEqual(_shown[0].title.rawtext[0].with.rawtext, [{ translate: table.messages.waystone_name }]);
});

test("a record stored before records carried a type is a waystone", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1", xp: 100 });
  _respond({ canceled: false, formValues: ["A"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  _respond({ canceled: false, formValues: ["B"] });
  await place(overworld, alex, { x: 5, y: 64, z: 0 });
  const key = core.recordKey("waystones", "minecraft:overworld", { x: 0, y: 64, z: 0 });
  const old = JSON.parse(world.getDynamicProperty(key));
  delete old.type;
  delete old.order;
  world.setDynamicProperty(key, JSON.stringify(old));
  _respond({ canceled: false, selection: 0 });
  use(overworld, alex, { x: 5, y: 64, z: 0 });
  _flush();
  await tick();
  assert.equal(alex.teleports.length, 1);
});

test("a waystone record left where a sharestone now stands is replaced, not reused", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { id: "1" });
  _respond({ canceled: false, formValues: ["Old"] });
  await place(overworld, alex, { x: 0, y: 64, z: 0 });
  const key = core.recordKey("waystones", "minecraft:overworld", { x: 0, y: 64, z: 0 });
  const old = JSON.parse(world.getDynamicProperty(key));
  overworld.set({ x: 0, y: 64, z: 0 }, ORANGE, { "minecraft:cardinal_direction": "north", [HALF]: "lower" });
  _respond({ canceled: true });
  use(overworld, alex, { x: 0, y: 64, z: 0 });
  const now = JSON.parse(world.getDynamicProperty(key));
  assert.notEqual(now.uid, old.uid);
  assert.equal(now.type, ORANGE);
  assert.equal(now.owner, null);
  assert.equal(alex.messages.length, 0);
});
