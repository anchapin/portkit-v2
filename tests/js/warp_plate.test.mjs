// The fixed waystone runtime's warp plates (src/portkit/runtime), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/warp_plate.test.mjs
// (tests/test_waystones.py runs it with PORTKIT_WAYSTONE_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../src/portkit/runtime/waystone_core.js";
import { registerWaystones } from "../../src/portkit/runtime/waystone.js";
import { _fire, _permutation, _runIntervals, _startup, world, GameMode, ItemStack } from "@minecraft/server";

const REQUIREMENTS = [
  { args: ["distance", 0.01], fn: "scaled_add_xp_cost", when: { is_interdimensional: false } },
  { args: [27], fn: "add_xp_cost", when: { is_interdimensional: true } },
  { args: [0.0], fn: "multiply_xp_cost", when: {} },
  { args: [0], fn: "min_xp_cost", when: {} },
  { args: [27], fn: "max_xp_cost", when: {} },
];

const FALLBACK = {
  block_types: { "waystones:waystone": "waystones:waystone" },
  blocks: ["waystones:waystone"],
  component: "waystones:portkit_waystone",
  default_type: "waystones:waystone",
  half_state: "waystones:half",
  messages: {
    invalid_target: "chat.waystones.warp_plate_has_invalid_target",
    no_target: "chat.waystones.warp_plate_has_no_target",
    not_enough_xp: "chat.waystones.not_enough_xp",
  },
  name_max_length: 128,
  namespace: "waystones",
  networks: { "waystones:waystone": { name: "waystone_name", none: "none", requirements: REQUIREMENTS, shared: false } },
  portstones: {},
  range_sq: 64,
  restricted_origins: ["PLAYER"],
  rune_blocks: [],
  rune_state: "waystones:runes",
  sounds: {
    activate: { id: "random.levelup", pitch: 1.0, volume: 0.2 },
    arrive: { id: "portal.travel", pitch: 1.0, volume: 0.05 },
    depart: { id: "portal.travel", pitch: 1.0, volume: 0.01 },
    eject: { id: "mob.chicken.plop", pitch: 1.0, volume: 1.0 },
  },
  warp_plates: {
    attunement_property: "waystones:portkit_attunement",
    attunement_ticks: 30,
    blocks: ["waystones:warp_plate"],
    component: "waystones:portkit_warp_plate",
    cooldown: 20,
    deny: ["minecraft:wither"],
    error_style: "\u00a74",
    requirements: REQUIREMENTS,
    shards: {
      accepted: ["waystones:attuned_shard", "waystones:crumbling_attuned_shard", "waystones:deepslate_shard",
        "waystones:dormant_shard"],
      attuned: "waystones:attuned_shard",
      dormant: "waystones:dormant_shard",
      locked: "waystones:deepslate_shard",
      single_use: ["waystones:crumbling_attuned_shard"],
    },
    status_state: "waystones:status",
    type: "waystones:warp_plate",
    use_time: 15,
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_WAYSTONE_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerWaystones(table);
const plates = table.warp_plates;
const component = _startup()[plates.component];
const PLATE = plates.blocks[0];
const STATUS = plates.status_state;
const PROP = plates.attunement_property;
const { dormant: DORMANT, attuned: ATTUNED, locked: LOCKED } = plates.shards;
const CRUMBLING = "waystones:crumbling_attuned_shard";

// -- a tiny world --------------------------------------------------------------

function makeDimension(id) {
  const blocks = new Map();
  const dimension = {
    id,
    sounds: [],
    spawned: [],
    entities: [],
    key: (p) => `${p.x},${p.y},${p.z}`,
    getBlock: (location) => blockAt(location),
    getEntities({ location, volume }) {
      return dimension.entities.filter((e) => e.dimension === dimension
        && e.location.x >= location.x && e.location.x < location.x + volume.x
        && e.location.y >= location.y && e.location.y < location.y + volume.y
        && e.location.z >= location.z && e.location.z < location.z + volume.z);
    },
    playSound(soundId, location, options) { dimension.sounds.push({ id: soundId, location, ...options }); },
    spawnItem(stack, location) { dimension.spawned.push({ stack, location }); return {}; },
    set(location, typeId, states) { blocks.set(dimension.key(location), _permutation(typeId, states)); },
    remove(location) { blocks.delete(dimension.key(location)); },
  };
  function blockAt(location) {
    const loc = { x: location.x, y: location.y, z: location.z };
    return {
      dimension,
      location: loc,
      get permutation() { return blocks.get(dimension.key(loc)) ?? _permutation("minecraft:air"); },
      get typeId() { return this.permutation.type.id; },
      setPermutation(p) { blocks.set(dimension.key(loc), p); },
    };
  }
  dimension.blockAt = blockAt;
  world._dimensions.set(id, dimension);
  return dimension;
}

let nextId = 100;

function makeEntity(dimension, location, { typeId = "minecraft:zombie", riding = false } = {}) {
  const entity = {
    id: String(nextId++),
    typeId,
    dimension,
    location: { ...location },
    isValid: true,
    teleports: [],
    getComponent: (id) => (id === "minecraft:riding" && riding ? {} : undefined),
    getRotation: () => ({ x: 12, y: 0 }),
    teleport(to, options) {
      this.teleports.push({ location: to, ...options });
      this.location = { ...to };
      if (options && options.dimension && options.dimension !== this.dimension) {
        this.dimension.entities.splice(this.dimension.entities.indexOf(this), 1);
        this.dimension = options.dimension;
        this.dimension.entities.push(this);
      }
    },
  };
  dimension.entities.push(entity);
  return entity;
}

function makePlayer(dimension, location, { xp = 0, creative = false, main, off } = {}) {
  const player = makeEntity(dimension, location ?? { x: 50, y: 64, z: 50 }, { typeId: "minecraft:player" });
  const slots = { Mainhand: main, Offhand: off };
  Object.assign(player, {
    name: "Alex",
    isSneaking: false,
    xp,
    actionbar: [],
    slots,
    getTotalXp() { return this.xp; },
    addExperience(n) { this.xp += n; return this.xp; },
    getGameMode: () => (creative ? GameMode.Creative : GameMode.Survival),
    onScreenDisplay: { setActionBar: (m) => player.actionbar.push(m) },
    getComponent(id) {
      if (id === "minecraft:equippable") {
        return { getEquipment: (s) => slots[s], setEquipment: (s, v) => { slots[s] = v; } };
      }
      return undefined;
    },
  });
  return player;
}

function clearWorld() {
  for (const key of world.getDynamicPropertyIds()) world.setDynamicProperty(key, undefined);
}

function place(dimension, player, location) {
  dimension.set(location, PLATE, { [STATUS]: "empty" });
  _fire("after", "playerPlaceBlock", { block: dimension.blockAt(location), player, dimension });
}

function status(dimension, location) {
  return dimension.blockAt(location).permutation.getState(STATUS);
}

function record(dimension, location) {
  return JSON.parse(world.getDynamicProperty(core.recordKey("waystones", dimension.id, location)));
}

/** One server tick: each plate's onTick, then the per-entity interval. */
function step(dimension, locations, n = 1) {
  for (let i = 0; i < n; i++) {
    for (const location of locations) {
      if (dimension.blockAt(location).typeId === PLATE) {
        component.onTick({ block: dimension.blockAt(location), dimension });
      }
    }
    _runIntervals();
  }
}

function use(dimension, player, location) {
  component.onPlayerInteract({ block: dimension.blockAt(location), dimension, player });
}

/** A plate placed by `player`, left to attune and pop its own shard; returns that shard. */
function attunedPlate(dimension, player, location) {
  place(dimension, player, location);
  step(dimension, [location], plates.attunement_ticks + 1);
  return dimension.spawned.at(-1).stack;
}

/** Plates at a and b, each holding a shard attuned to the other. */
function linked(dimension, player, a, b) {
  const shardA = attunedPlate(dimension, player, a);
  const shardB = attunedPlate(dimension, player, b);
  player.slots.Mainhand = shardA;
  use(dimension, player, b);
  player.slots.Mainhand = shardB;
  use(dimension, player, a);
}

const A = { x: 0, y: 64, z: 0 };
const B = { x: 100, y: 64, z: 0 };
const on = (p) => ({ x: p.x + 0.5, y: p.y + 0.125, z: p.z + 0.5 });

// -- core ----------------------------------------------------------------------

test("idle status: empty, locked, attuning, else idle", () => {
  const s = plates.shards;
  assert.equal(core.idleStatus(null, s), "empty");
  assert.equal(core.idleStatus({ id: LOCKED }, s), "locked");
  assert.equal(core.idleStatus({ id: DORMANT }, s), "attuning");
  assert.equal(core.idleStatus({ id: ATTUNED, attunement: "x" }, s), "idle");
  assert.equal(core.hasPotentialTarget({ id: LOCKED }, s), false);
  assert.equal(core.hasPotentialTarget({ id: DORMANT }, s), true);
});

test("target: the shard's attunement unless it is the plate's own", () => {
  const s = plates.shards;
  assert.equal(core.targetUid({ id: ATTUNED, attunement: "b" }, s, "a"), "b");
  assert.equal(core.targetUid({ id: ATTUNED, attunement: "a" }, s, "a"), null);
  assert.equal(core.targetUid({ id: CRUMBLING, attunement: null }, s, "a"), null);
  assert.equal(core.targetUid(null, s, "a"), null);
});

test("entity cooldown: counts down only off its plate, starts over on it", () => {
  const t = core.newTracking();
  core.markCooldown(t, "p", 20);
  core.entityTick(t, false, 20);
  assert.equal(t.since, 19);
  core.entityTick(t, true, 20);
  assert.equal(t.since, 20);
  assert.equal(core.onCooldown(t, "p"), true);
  assert.equal(core.onCooldown(t, "q"), false);
});

// -- placing and attuning ------------------------------------------------------

test("a placed plate holds a dormant shard, attunes it in 30 ticks and pops it out", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  place(overworld, alex, A);
  const placed = record(overworld, A);
  assert.equal(placed.owner, alex.id);
  assert.equal(placed.type, plates.type);
  assert.deepEqual(placed.shard, { id: DORMANT, attunement: null });
  assert.equal(status(overworld, A), "attuning");
  step(overworld, [A], plates.attunement_ticks - 1);
  assert.equal(record(overworld, A).shard.id, DORMANT);
  step(overworld, [A]);
  assert.deepEqual(record(overworld, A).shard, { id: ATTUNED, attunement: placed.uid });
  assert.equal(status(overworld, A), "idle");
  assert.equal(overworld.spawned.length, 0);
  step(overworld, [A]);
  assert.equal(record(overworld, A).shard, null);
  assert.equal(status(overworld, A), "empty");
  const popped = overworld.spawned.at(-1);
  assert.equal(popped.stack.typeId, ATTUNED);
  assert.equal(popped.stack.getDynamicProperty(PROP), placed.uid);
  assert.deepEqual(popped.location, { x: 0.5, y: 64.5, z: 0.5 });
  assert.deepEqual(overworld.sounds.at(-1), { id: "mob.chicken.plop", location: popped.location, volume: 1.0, pitch: 1.0 });
});

test("a plate with no record (placed by command) gets one with a dormant shard on its first tick", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  overworld.set(A, PLATE, { [STATUS]: "empty" });
  step(overworld, [A]);
  const made = record(overworld, A);
  assert.equal(made.owner, null);
  assert.equal(made.origin, "UNKNOWN");
  assert.equal(made.shard.id, DORMANT);
});

// -- shards in and out ---------------------------------------------------------

test("a warp shard goes in when the plate is empty; survival uses it up, creative keeps it", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  const shard = attunedPlate(overworld, alex, A);
  place(overworld, alex, B);
  step(overworld, [B], plates.attunement_ticks + 1);
  alex.slots.Mainhand = shard;
  use(overworld, alex, B);
  assert.equal(alex.slots.Mainhand, undefined);
  assert.deepEqual(record(overworld, B).shard.attunement, record(overworld, A).uid);
  assert.equal(status(overworld, B), "idle");
  // Full: a second shard does nothing.
  const other = new ItemStack(DORMANT, 3);
  alex.slots.Mainhand = other;
  use(overworld, alex, B);
  assert.equal(other.amount, 3);
  const steve = makePlayer(overworld, undefined, { creative: true, main: new ItemStack(DORMANT, 1) });
  overworld.set({ x: 5, y: 64, z: 5 }, PLATE, { [STATUS]: "empty" });
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, { x: 5, y: 64, z: 5 }), JSON.stringify({
    uid: "c", type: plates.type, dimension: overworld.id, pos: { x: 5, y: 64, z: 5 }, shard: null }));
  use(overworld, steve, { x: 5, y: 64, z: 5 });
  assert.equal(steve.slots.Mainhand.amount, 1);
  assert.equal(status(overworld, { x: 5, y: 64, z: 5 }), "attuning");
});

test("sneaking with empty hands pops the shard out; sneaking with an item does nothing", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  place(overworld, alex, A);
  alex.isSneaking = true;
  alex.slots.Offhand = new ItemStack("minecraft:torch", 1);
  use(overworld, alex, A);
  assert.equal(record(overworld, A).shard.id, DORMANT);
  alex.slots.Offhand = undefined;
  use(overworld, alex, A);
  assert.equal(record(overworld, A).shard, null);
  assert.equal(overworld.spawned.at(-1).stack.typeId, DORMANT);
  assert.equal(status(overworld, A), "empty");
});

test("a deepslate shard locks the plate: nothing warps", { skip: !LOCKED }, () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  attunedPlate(overworld, alex, A);
  alex.slots.Mainhand = new ItemStack(LOCKED, 1);
  use(overworld, alex, A);
  assert.equal(status(overworld, A), "locked");
  const zombie = makeEntity(overworld, on(A));
  step(overworld, [A], 40);
  assert.equal(zombie.teleports.length, 0);
  assert.equal(status(overworld, A), "locked");
});

// -- warping -------------------------------------------------------------------

test("standing on a plate warps to the plate its shard names after the use time, onto its centre", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  linked(overworld, alex, A, B);
  alex.location = on(B);
  step(overworld, [A, B]);
  assert.equal(status(overworld, B), "warping");
  step(overworld, [A, B], plates.use_time);
  assert.equal(alex.teleports.length, 0);
  step(overworld, [A, B]);
  assert.equal(alex.teleports.length, 1);
  const hop = alex.teleports[0];
  assert.deepEqual(hop.location, { x: 0.5, y: 64.5, z: 0.5 });
  assert.equal(hop.rotation.y, -180);
  assert.equal(hop.dimension, overworld);
  assert.equal(alex.xp, 0); // free: source_is_warp_plate multiplies the cost by 0
  assert.deepEqual(overworld.sounds.slice(-2).map((s) => [s.id, s.volume]), [["portal.travel", 0.01], ["portal.travel", 0.05]]);
});

test("an arrival does not warp back while it stays, nor until it has been off for the cooldown", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  linked(overworld, alex, A, B);
  alex.location = on(B);
  step(overworld, [A, B], plates.use_time + 2);
  assert.equal(alex.teleports.length, 1);
  alex.location = on(A);
  step(overworld, [A, B], 60);
  assert.equal(alex.teleports.length, 1);
  assert.equal(status(overworld, A), "idle");
  // Off for less than the cooldown, then back: still nothing.
  alex.location = { x: 3, y: 64, z: 3 };
  step(overworld, [A, B], plates.cooldown - 2);
  alex.location = on(A);
  step(overworld, [A, B], plates.use_time + 5);
  assert.equal(alex.teleports.length, 1);
  // Off for the whole cooldown: it warps again.
  alex.location = { x: 3, y: 64, z: 3 };
  step(overworld, [A, B], plates.cooldown + 1);
  alex.location = on(A);
  step(overworld, [A, B], plates.use_time + 2);
  assert.equal(alex.teleports.length, 2);
  assert.deepEqual(alex.location, { x: 100.5, y: 64.5, z: 0.5 });
});

test("mobs and items warp too; the deny list and riders do not", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  linked(overworld, alex, A, B);
  const zombie = makeEntity(overworld, on(B));
  const item = makeEntity(overworld, on(B), { typeId: "minecraft:item" });
  const wither = makeEntity(overworld, on(B), { typeId: plates.deny[0] });
  const rider = makeEntity(overworld, on(B), { riding: true });
  step(overworld, [A, B], plates.use_time + 2);
  assert.equal(zombie.teleports.length, 1);
  assert.equal(item.teleports.length, 1);
  assert.equal(wither.teleports.length, 0);
  assert.equal(rider.teleports.length, 0);
});

test("stepping off before the use time cancels the warp and the plate goes idle", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  linked(overworld, alex, A, B);
  alex.location = on(B);
  step(overworld, [A, B], 5);
  alex.location = { x: 90, y: 64, z: 0 };
  step(overworld, [A, B]);
  assert.equal(status(overworld, B), "idle");
  alex.location = on(B);
  step(overworld, [A, B], plates.use_time);
  assert.equal(alex.teleports.length, 0);
});

test("a shard with no attunement: the plate turns invalid and the player is told it has no target", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  attunedPlate(overworld, alex, A);
  alex.slots.Mainhand = new ItemStack(CRUMBLING, 1); // a stackable shard carries no attunement here
  use(overworld, alex, A);
  assert.equal(status(overworld, A), "idle");
  alex.location = on(A);
  step(overworld, [A]);
  assert.equal(status(overworld, A), "warping_invalid");
  step(overworld, [A], plates.use_time + 1);
  assert.equal(alex.teleports.length, 0);
  assert.deepEqual(alex.actionbar.at(-1), { rawtext: [{ text: plates.error_style }, { translate: table.messages.no_target }] });
});

test("a target plate that was broken: the player is told the shard lost its attunement", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  linked(overworld, alex, A, B);
  component.onPlayerBreak({ block: overworld.blockAt(A), dimension: overworld, player: alex, brokenBlockPermutation: overworld.blockAt(A).permutation });
  overworld.remove(A);
  alex.location = on(B);
  step(overworld, [B], plates.use_time + 2);
  assert.equal(alex.teleports.length, 0);
  assert.deepEqual(alex.actionbar.at(-1).rawtext[1], { translate: table.messages.invalid_target });
});

test("breaking a plate drops its shard outside creative and forgets the plate", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  place(overworld, alex, A);
  const before = overworld.spawned.length;
  component.onPlayerBreak({ block: overworld.blockAt(A), dimension: overworld, player: alex, brokenBlockPermutation: overworld.blockAt(A).permutation });
  assert.equal(overworld.spawned.length, before + 1);
  assert.equal(overworld.spawned.at(-1).stack.typeId, DORMANT);
  assert.equal(world.getDynamicProperty(core.recordKey("waystones", overworld.id, A)), undefined);
  const steve = makePlayer(overworld, undefined, { creative: true });
  place(overworld, steve, B);
  component.onPlayerBreak({ block: overworld.blockAt(B), dimension: overworld, player: steve, brokenBlockPermutation: overworld.blockAt(B).permutation });
  assert.equal(overworld.spawned.length, before + 1);
});

test("an attuned shard's attunement survives being put in and popped out again", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  const shard = attunedPlate(overworld, alex, A);
  place(overworld, alex, B);
  step(overworld, [B], plates.attunement_ticks + 1);
  alex.slots.Mainhand = shard;
  use(overworld, alex, B);
  alex.isSneaking = true;
  use(overworld, alex, B);
  const back = overworld.spawned.at(-1).stack;
  assert.equal(back.typeId, ATTUNED);
  assert.equal(back.getDynamicProperty(PROP), record(overworld, A).uid);
});
