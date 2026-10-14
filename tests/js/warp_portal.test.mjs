// The fixed waystone runtime's warp portals and portal scroll (src/portkit/runtime), offline under node.
// Run: node --import ./tests/js/register.mjs --test tests/js/warp_portal.test.mjs
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
const SCROLL_REQUIREMENTS = [...REQUIREMENTS.slice(0, 2), { args: [0.0], fn: "multiply_xp_cost", when: {} },
  ...REQUIREMENTS.slice(2)];

const FALLBACK = {
  block_types: { "waystones:waystone": "waystones:waystone" },
  blocks: ["waystones:waystone"],
  component: "waystones:portkit_waystone",
  default_type: "waystones:waystone",
  half_state: "waystones:half",
  messages: {
    attunement_lost: "chat.waystones.warp_portal_attunement_lost",
    current_location: "gui.waystones.waystone_selection.current_location",
    missing: "chat.waystones.waystone_missing",
    no_space: "chat.waystones.warp_portal_no_space",
    none: "gui.waystones.waystone_selection.no_waystones_activated",
    not_enough_xp: "chat.waystones.not_enough_xp",
    out_of_range: "chat.waystones.source_waystone_out_of_range",
    return_to_portal: "gui.waystones.waystone_selection.return_to_portal",
    title: "container.waystones.waystone_selection",
    unnamed: "gui.waystones.waystone_selection.unnamed_waystone",
    xp_cost: "gui.waystones.waystone_selection.xp_requirement",
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
    return_requirements: { "waystones:waystone": REQUIREMENTS },
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
const portals = table.warp_portals;
const registered = _startup();
const portalComponent = registered[portals.component];
const waystoneComponent = registered[table.component];
const PORTAL = portals.blocks[0];
const SCROLL = portals.scroll.items[0];
const HALF = table.half_state;
const WAYSTONE = Object.keys(table.block_types).find((id) => table.block_types[id] === portals.scroll.network);
const settle = () => new Promise((resolve) => setImmediate(resolve));

// -- a tiny world: stone at y <= 63, air above ------------------------------------

function makeDimension(id) {
  const blocks = new Map();
  const dimension = {
    id,
    sounds: [],
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
      setPermutation(p) { blocks.set(dimension.key(loc), p); },
      setType(typeId) { blocks.set(dimension.key(loc), _permutation(typeId)); },
    };
  }
  dimension.blockAt = blockAt;
  world._dimensions.set(id, dimension);
  return dimension;
}

let nextId = 500;

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
    },
  };
  dimension.entities.push(entity);
  return entity;
}

function makePlayer(dimension, location, { xp = 0, creative = false, scrolls = 2, yaw = 0, view } = {}) {
  const player = makeEntity(dimension, location ?? { x: 0.5, y: 64, z: 0.5 }, { typeId: "minecraft:player" });
  const slots = [scrolls ? new ItemStack(SCROLL, scrolls) : undefined, new ItemStack("minecraft:stick", 1)];
  const props = {};
  Object.assign(player, {
    name: "Alex",
    isSneaking: false,
    xp,
    actionbar: [],
    chat: [],
    slots,
    selectedSlotIndex: 0,
    view: view ?? { x: 0, y: 0, z: 1 },
    getViewDirection() { return this.view; },
    getRotation: () => ({ x: 12, y: yaw }),
    getTotalXp() { return this.xp; },
    addExperience(n) { this.xp += n; return this.xp; },
    getGameMode: () => (creative ? GameMode.Creative : GameMode.Survival),
    sendMessage(m) { this.chat.push(m); },
    onScreenDisplay: { setActionBar: (m) => player.actionbar.push(m) },
    getDynamicProperty: (key) => props[key],
    setDynamicProperty: (key, value) => { props[key] = value; },
    getComponent(id) {
      if (id === "minecraft:inventory") {
        return { container: { getItem: (i) => slots[i], setItem: (i, v) => { slots[i] = v; } } };
      }
      return undefined;
    },
  });
  return player;
}

function clearWorld() {
  for (const key of world.getDynamicPropertyIds()) world.setDynamicProperty(key, undefined);
  _reset();
}

function record(dimension, pos) {
  const raw = world.getDynamicProperty(core.recordKey("waystones", dimension.id, pos));
  return raw === undefined ? undefined : JSON.parse(raw);
}

/** A waystone at `pos` facing north, stored and activated for each of `players`. */
function waystone(dimension, pos, name, ...players) {
  dimension.set(pos, WAYSTONE, { [HALF]: "lower", "minecraft:cardinal_direction": "north" });
  dimension.set({ ...pos, y: pos.y + 1 }, WAYSTONE, { [HALF]: "upper", "minecraft:cardinal_direction": "north" });
  const uid = `w${nextId++}`;
  world.setDynamicProperty(core.recordKey("waystones", dimension.id, pos), JSON.stringify({
    uid, type: portals.scroll.network, order: 1, dimension: dimension.id, pos, facing: "north",
    name: { text: name }, owner: null, origin: "PLAYER" }));
  for (const player of players) {
    player.setDynamicProperty(core.activatedKey("waystones"), JSON.stringify([uid]));
  }
  return uid;
}

/** One server tick: the portal's lower and upper halves' onTick, then the intervals. */
function tick(dimension, pos, n = 1) {
  for (let i = 0; i < n; i++) {
    for (const at of [pos, { ...pos, y: pos.y + 1 }]) {
      const block = dimension.blockAt(at);
      if (block.typeId === PORTAL) portalComponent.onTick({ block, dimension });
    }
    _runIntervals();
  }
}

function useScroll(player) {
  _fire("after", "itemUse", { source: player, itemStack: player.slots[player.selectedSlotIndex] });
}

/** Hold a scroll for its use time, choose menu entry `choice`, and let the menu answer. */
async function openWith(player, choice = 0) {
  useScroll(player);
  for (let i = 0; i < portals.scroll.use_time; i++) _runIntervals();
  _respond({ canceled: false, selection: choice });
  _flush();
  await settle();
}

const P = { x: 0, y: 64, z: 3 }; // where a player at 0.5,64,0.5 looking south opens a portal
const W = { x: 100, y: 64, z: 0 };

// -- core ----------------------------------------------------------------------

test("a portal faces the player: Direction.fromYRot(yaw).getOpposite()", () => {
  assert.equal(core.portalFacing(0), "north"); // looking south
  assert.equal(core.portalFacing(90), "east"); // looking west
  assert.equal(core.portalFacing(180), "south");
  assert.equal(core.portalFacing(-90), "west");
  assert.equal(core.portalFacing(44), "north");
  assert.equal(core.portalFacing(46), "east");
  assert.equal(core.portalFacing(-180), "south");
});

test("findPortalPos: 3 then 4 blocks out, from 2 above the feet down 5", () => {
  const tried = [];
  const pos = core.portalPos({ x: 0.5, y: 64, z: 0.5 }, { x: 0, y: -0.3, z: 0.9 }, (p) => {
    tried.push(p);
    return p.y === 64 && p.z === 4;
  });
  assert.deepEqual(pos, { x: 0, y: 64, z: 4 });
  assert.deepEqual(tried.slice(0, 6).map((p) => p.y), [66, 65, 64, 63, 62, 61]);
  assert.ok(tried.slice(0, 6).every((p) => p.z === 3));
  assert.equal(core.portalPos({ x: 0, y: 64, z: 0 }, { x: 0, y: 1, z: 0 }, () => true), null);
});

test("an entity uses a portal at most once per cooldown", () => {
  const uses = new Map();
  assert.equal(core.mayUsePortal(uses, "a", 100, 20), true);
  assert.equal(core.mayUsePortal(uses, "a", 119, 20), false);
  assert.equal(core.mayUsePortal(uses, "a", 120, 20), true);
});

// -- the portal scroll -----------------------------------------------------------

test("holding a portal scroll for its use time opens the menu of activated waystones; a choice opens the portal", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  waystone(overworld, W, "Home", alex);
  useScroll(alex);
  assert.deepEqual(overworld.sounds.at(-1), { id: "portal.trigger", location: alex.location, volume: 0.1, pitch: 2.0 });
  for (let i = 0; i < portals.scroll.use_time - 1; i++) _runIntervals();
  _flush();
  assert.equal(_shown.length, 0);
  _runIntervals();
  _respond({ canceled: false, selection: 0 });
  _flush();
  await settle();
  const form = _shown.at(-1);
  assert.deepEqual(form.title, { translate: "container.waystones.waystone_selection" });
  assert.deepEqual(form.buttons.map((b) => b.text.rawtext[0]), [{ text: "Home" }]);
  // The scroll's menu shows no cost (source_is_scroll multiplies it by 0).
  assert.equal(form.buttons[0].text.rawtext.length, 1);
  const lower = overworld.blockAt(P).permutation;
  const upper = overworld.blockAt({ ...P, y: 65 }).permutation;
  assert.equal(lower.type.id, PORTAL);
  assert.equal(lower.getState(HALF), "lower");
  assert.equal(upper.getState(HALF), "upper");
  assert.equal(lower.getState("minecraft:cardinal_direction"), "north");
  const made = record(overworld, P);
  assert.equal(made.type, portals.type);
  assert.equal(made.target, record(overworld, W).uid);
  assert.equal(made.facing, "north");
  assert.deepEqual(made.name, { translate: "gui.waystones.waystone_selection.return_to_portal" });
  assert.deepEqual(overworld.sounds.at(-1), { id: "portal.travel", location: { x: 0.5, y: 64.5, z: 3.5 },
    volume: 0.25, pitch: 1.4 });
  assert.equal(alex.slots[0].amount, 1);
});

test("the last scroll goes; a creative player keeps theirs", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, undefined, { scrolls: 1 });
  waystone(overworld, W, "Home", alex);
  await openWith(alex);
  assert.equal(alex.slots[0], undefined);
  clearWorld();
  const nether = makeDimension("minecraft:the_nether");
  const steve = makePlayer(nether, undefined, { scrolls: 1, creative: true });
  waystone(nether, W, "Home", steve);
  await openWith(steve);
  assert.equal(steve.slots[0].amount, 1);
  assert.equal(nether.blockAt(P).typeId, PORTAL);
});

test("switching away from the scroll or taking damage stops its use", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  waystone(overworld, W, "Home", alex);
  useScroll(alex);
  _runIntervals();
  alex.selectedSlotIndex = 1;
  for (let i = 0; i < portals.scroll.use_time; i++) _runIntervals();
  alex.selectedSlotIndex = 0;
  _flush();
  assert.equal(_shown.length, 0);
  useScroll(alex);
  _runIntervals();
  _fire("after", "entityHurt", { hurtEntity: alex, damage: 1 });
  for (let i = 0; i < portals.scroll.use_time; i++) _runIntervals();
  _flush();
  assert.equal(_shown.length, 0);
});

test("no room for a portal says so instead of opening the menu", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, undefined, { view: { x: 0, y: 1, z: 0 } });
  waystone(overworld, W, "Home", alex);
  useScroll(alex);
  for (let i = 0; i < portals.scroll.use_time; i++) _runIntervals();
  _flush();
  assert.equal(_shown.length, 0);
  assert.deepEqual(alex.chat.at(-1), { rawtext: [{ text: "\u00a74" }, { translate: "chat.waystones.warp_portal_no_space" }] });
  // A wall where the portal would stand leaves no room either.
  const steve = makePlayer(overworld);
  for (let y = 58; y <= 70; y++) {
    for (const z of [3, 4]) overworld.set({ x: 0, y, z }, "minecraft:stone");
  }
  useScroll(steve);
  for (let i = 0; i < portals.scroll.use_time; i++) _runIntervals();
  _flush();
  assert.equal(steve.chat.length, 1);
});

// -- going through ---------------------------------------------------------------

test("an entity in either half goes beside the target waystone; a player pays and keeps the return portal", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, undefined, { xp: 10 });
  waystone(overworld, W, "Home", alex);
  await openWith(alex);
  const portalUid = record(overworld, P).uid;
  alex.location = { x: 0.5, y: 65.2, z: 3.5 }; // in the upper half
  tick(overworld, P);
  // Beside the waystone on its facing side (north), facing north.
  assert.deepEqual(alex.location, { x: 100.5, y: 64.5, z: -0.5 });
  const cost = core.cost(portals.requirements, { is_interdimensional: false,
    distance: core.distance({ x: 0.5, y: 65.2, z: 3.5 }, W) });
  assert.ok(cost > 0);
  assert.equal(alex.xp, 10 - cost);
  assert.equal(alex.getDynamicProperty(portals.return_property), portalUid);
  const zombie = makeEntity(overworld, { x: 0.5, y: 64, z: 3.5 });
  tick(overworld, P);
  assert.deepEqual(zombie.location, { x: 100.5, y: 64.5, z: -0.5 });
  const wither = makeEntity(overworld, { x: 0.5, y: 64, z: 3.5 }, { typeId: "minecraft:wither" });
  const rider = makeEntity(overworld, { x: 0.5, y: 64, z: 3.5 }, { riding: true });
  tick(overworld, P);
  assert.equal(wither.teleports.length, 0);
  assert.equal(rider.teleports.length, 0);
});

test("an entity uses a portal at most once every 20 ticks", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  waystone(overworld, W, "Home", alex);
  await openWith(alex);
  const zombie = makeEntity(overworld, { x: 0.5, y: 64, z: 3.5 });
  tick(overworld, P);
  assert.equal(zombie.teleports.length, 1);
  zombie.location = { x: 0.5, y: 64, z: 3.5 };
  tick(overworld, P, portals.cooldown - 1);
  assert.equal(zombie.teleports.length, 1);
  tick(overworld, P);
  assert.equal(zombie.teleports.length, 2);
});

test("a player who can't pay is told on the action bar and stays", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { x: 0.5, y: 64, z: 0.5 });
  waystone(overworld, W, "Home", alex);
  await openWith(alex);
  alex.location = { x: 0.5, y: 64, z: 3.5 };
  tick(overworld, P);
  assert.equal(alex.teleports.length, 0);
  assert.deepEqual(alex.actionbar.at(-1), { rawtext: [{ text: "\u00a74" }, { translate: "chat.waystones.not_enough_xp" }] });
});

test("a portal whose waystone is gone closes when something enters, telling a player", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, undefined, { xp: 100 });
  waystone(overworld, W, "Home", alex);
  await openWith(alex);
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, W), undefined);
  alex.location = { x: 0.5, y: 64, z: 3.5 };
  tick(overworld, P);
  assert.deepEqual(alex.chat.at(-1), { rawtext: [{ translate: "chat.waystones.warp_portal_attunement_lost" }] });
  assert.equal(overworld.blockAt(P).typeId, "minecraft:air");
  assert.equal(overworld.blockAt({ ...P, y: 65 }).typeId, "minecraft:air");
  assert.equal(record(overworld, P), undefined);
  assert.deepEqual(overworld.sounds.at(-1), { id: "random.fizz", location: { x: 0.5, y: 64.5, z: 3.5 },
    volume: 0.5, pitch: 1.2 });
});

test("a portal closes after its lifetime", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld);
  waystone(overworld, W, "Home", alex);
  await openWith(alex);
  tick(overworld, P, portals.lifetime - 1);
  assert.equal(overworld.blockAt(P).typeId, PORTAL);
  assert.equal(record(overworld, P).age, Math.floor((portals.lifetime - 1) / 20) * 20);
  tick(overworld, P);
  assert.equal(overworld.blockAt(P).typeId, "minecraft:air");
  assert.equal(record(overworld, P), undefined);
});

test("a portal placed by command has no target and closes on the first entity", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  overworld.set(P, PORTAL, { [HALF]: "lower", "minecraft:cardinal_direction": "east" });
  overworld.set({ ...P, y: 65 }, PORTAL, { [HALF]: "upper", "minecraft:cardinal_direction": "east" });
  tick(overworld, P);
  assert.equal(record(overworld, P).target, null);
  makeEntity(overworld, { x: 0.5, y: 64, z: 3.5 });
  tick(overworld, P);
  assert.equal(overworld.blockAt(P).typeId, "minecraft:air");
});

// -- return to portal --------------------------------------------------------------

test("a waystone's menu ends with Return to Portal while the portal stands, and it takes the player back", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, undefined, { xp: 100 });
  waystone(overworld, W, "Home", alex);
  await openWith(alex);
  alex.location = { x: 0.5, y: 64, z: 3.5 };
  tick(overworld, P);
  // At the waystone: use it, choose the last entry.
  const block = overworld.blockAt(W);
  _respond({ canceled: false, selection: 0 });
  waystoneComponent.onPlayerInteract({ block, dimension: overworld, player: alex });
  _flush();
  await settle();
  const form = _shown.at(-1);
  assert.deepEqual(form.buttons.map((b) => b.text.rawtext[0]),
    [{ translate: "gui.waystones.waystone_selection.return_to_portal" }]);
  // Beside the portal on its facing side (north of it: z 2).
  assert.deepEqual(alex.location, { x: 0.5, y: 64.5, z: 2.5 });
  // Gone portal: no entry.
  tick(overworld, P, portals.lifetime);
  waystoneComponent.onPlayerInteract({ block, dimension: overworld, player: alex });
  _flush();
  await settle();
  assert.deepEqual(_shown.at(-1).buttons, []);
});
