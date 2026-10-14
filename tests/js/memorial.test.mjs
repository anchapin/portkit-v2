// The fixed waystone runtime's fleeting memorials (src/portkit/runtime), offline under node.
// Run: node --import ./tests/js/register.mjs --test tests/js/memorial.test.mjs
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
// target_is_fleeting_memorial multiply_xp_cost(0) before the clamp: free.
const TO_MEMORIAL = [...REQUIREMENTS.slice(0, 2), { args: [0.0], fn: "multiply_xp_cost", when: {} },
  ...REQUIREMENTS.slice(2)];
const SCROLL = [...REQUIREMENTS.slice(0, 2), { args: [0.0], fn: "multiply_xp_cost", when: {} },
  ...REQUIREMENTS.slice(2)];
const BY_TYPE = {
  "waystones:waystone": REQUIREMENTS,
  "waystones:orange_sharestone": REQUIREMENTS,
  "waystones:warp_portal": REQUIREMENTS,
  "waystones:fleeting_memorial": TO_MEMORIAL,
};

const FALLBACK = {
  block_types: { "waystones:waystone": "waystones:waystone", "waystones:orange_sharestone": "waystones:orange_sharestone" },
  blocks: ["waystones:orange_sharestone", "waystones:waystone", "waystones:white_portstone"],
  component: "waystones:portkit_waystone",
  default_type: "waystones:waystone",
  fleeting_memorials: {
    blocks: ["waystones:fleeting_memorial"],
    drop_radius: 2,
    epitaph_style: "\u00a7d",
    epitaphs: ["waystones:epitaph"],
    requirements: { "waystones:waystone": TO_MEMORIAL, "waystones:orange_sharestone": TO_MEMORIAL },
    search_height: 3,
    search_radius: 2,
    type: "waystones:fleeting_memorial",
  },
  half_state: "waystones:half",
  messages: {
    activated: "chat.waystones.waystone_activated",
    attunement_lost: "chat.waystones.warp_portal_attunement_lost",
    current_location: "gui.waystones.waystone_selection.current_location",
    epitaph: "item.waystones:epitaph.name",
    epitaph_requirement: "gui.waystones.waystone_selection.epitaph_requirement",
    memorial_name: "tile.waystones:fleeting_memorial.name",
    missing: "chat.waystones.waystone_missing",
    none: "gui.waystones.waystone_selection.no_waystones_activated",
    none_shared: "gui.waystones.waystone_selection.no_sharestones_available",
    not_enough_xp: "chat.waystones.not_enough_xp",
    only_owner: "chat.waystones.only_owner_can_edit",
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
  portstones: {
    "waystones:white_portstone": { requirements: REQUIREMENTS, target: "waystones:waystone",
      title: "container.waystones.white_portstone" },
  },
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
      "waystones:bound_scroll": { kind: "bound", requirements: { ...BY_TYPE, "waystones:fleeting_memorial": SCROLL } },
      "waystones:warp_scroll": { kind: "warp", requirements: { ...BY_TYPE, "waystones:fleeting_memorial": SCROLL } },
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
    epitaph: { id: "random.totem", pitch: 1.0, volume: 1.0 },
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
    memorial_requirements: TO_MEMORIAL,
    requirements: REQUIREMENTS,
    return_property: "waystones:portkit_return_portal",
    return_requirements: { "waystones:waystone": REQUIREMENTS, "waystones:orange_sharestone": REQUIREMENTS },
    scroll: {
      items: ["waystones:portal_scroll"],
      memorial_requirements: SCROLL,
      network: "waystones:waystone",
      requirements: SCROLL,
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
const registered = _startup();
const component = registered[table.component];
const portalComponent = table.warp_portals ? registered[table.warp_portals.component] : undefined;
const mem = table.fleeting_memorials;
const MEMORIAL = mem.blocks[0];
const EPITAPH = mem.epitaphs[0];
const HALF = table.half_state;
const WAYSTONE = Object.keys(table.block_types).find((id) => table.block_types[id] === "waystones:waystone");
const SHARESTONE = Object.keys(table.block_types).find((id) => table.block_types[id] !== "waystones:waystone");
const PORTSTONE = Object.keys(table.portstones || {}).find((id) => table.portstones[id].target === "waystones:waystone");
const settle = () => new Promise((resolve) => setImmediate(resolve));

// -- a tiny world: stone at y <= 63, air above ------------------------------------

function makeDimension(id) {
  const blocks = new Map();
  const dimension = {
    id,
    sounds: [],
    spawned: [],
    entities: [],
    commands: [],
    heightRange: { min: -64, max: 320 },
    key: (p) => `${p.x},${p.y},${p.z}`,
    getBlock: (location) => blockAt(location),
    getEntities(options) {
      return dimension.entities.filter((e) => {
        if (!e.isValid || e.dimension !== dimension) return false;
        if (options.type && e.typeId !== options.type) return false;
        if (options.volume) {
          const { location: l, volume: v } = options;
          return e.location.x >= l.x && e.location.x < l.x + v.x && e.location.y >= l.y && e.location.y < l.y + v.y
            && e.location.z >= l.z && e.location.z < l.z + v.z;
        }
        if (options.maxDistance !== undefined) {
          const d = Math.hypot(e.location.x - options.location.x, e.location.y - options.location.y,
            e.location.z - options.location.z);
          return d <= options.maxDistance;
        }
        return true;
      });
    },
    playSound(soundId, location, options) { dimension.sounds.push({ id: soundId, location, ...options }); },
    spawnItem(stack, location) { return dropItem(dimension, stack, location); },
    runCommand(command) {
      dimension.commands.push(command);
      const m = /^setblock (-?\d+) (-?\d+) (-?\d+) air destroy$/.exec(command);
      if (m) dimension.set({ x: +m[1], y: +m[2], z: +m[3] }, "minecraft:air");
      return { successCount: 1 };
    },
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

let nextId = 700;

/** An item entity lying at `location` holding `stack`. */
function dropItem(dimension, stack, location) {
  const entity = {
    id: String(nextId++),
    typeId: "minecraft:item",
    dimension,
    location: { ...location },
    isValid: true,
    getComponent: (id) => (id === "minecraft:item" ? { itemStack: stack } : undefined),
    remove() { this.isValid = false; },
  };
  dimension.entities.push(entity);
  return entity;
}

const SLOTS = 36;

function makePlayer(dimension, { held, location, yaw = 0, xp = 0, creative = false, offhand } = {}) {
  const slots = new Array(SLOTS).fill(undefined);
  slots[0] = held;
  const equipment = { Offhand: offhand };
  const props = {};
  const container = {
    size: SLOTS,
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
    heard: [],
    slots,
    equipment,
    selectedSlotIndex: 0,
    getRotation: () => ({ x: 12, y: yaw }),
    getViewDirection: () => ({ x: 0, y: 0, z: 1 }),
    getTotalXp() { return this.xp; },
    addExperience(n) { this.xp += n; return this.xp; },
    getGameMode: () => (creative ? GameMode.Creative : GameMode.Survival),
    sendMessage(m) { this.chat.push(m); },
    playSound(id, options) { this.heard.push({ id, ...options }); },
    onScreenDisplay: { setActionBar: (m) => player.actionbar.push(m) },
    getDynamicProperty: (key) => props[key],
    setDynamicProperty: (key, value) => { props[key] = value; },
    getComponent(id) {
      if (id === "minecraft:inventory") return { container };
      if (id === "minecraft:equippable") {
        return { getEquipment: (s) => equipment[s], setEquipment: (s, v) => { equipment[s] = v; } };
      }
      return undefined;
    },
    teleport(to, options) {
      this.teleports.push({ location: to, ...options });
      this.location = { ...to };
      if (options && options.dimension) this.dimension = options.dimension;
    },
  };
  dimension.entities.push(player);
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

function die(player) {
  _fire("after", "entityDie", { deadEntity: player, damageSource: {} });
}

function interact(dimension, pos, player) {
  component.onPlayerInteract({ block: dimension.blockAt(pos), dimension, player });
}

/** Die with an epitaph in hand at `location` (facing `yaw`); returns where the memorial went. */
function dieWithEpitaph(dimension, location, yaw = 0) {
  const ghost = makePlayer(dimension, { held: new ItemStack(EPITAPH, 1), location, yaw });
  die(ghost);
  return ghost;
}

const NAME = { translate: table.messages.memorial_name };
const W = { x: 100, y: 64, z: 0 };
const BESIDE_W = { x: 100.5, y: 64.5, z: -0.5 };
const DEATH = { x: 20.5, y: 64, z: 30.5 };
const ABOVE = { x: 20, y: 65, z: 30 };
const error = (key) => ({ rawtext: [{ text: "\u00a74" }, { translate: key }] });

// -- core ----------------------------------------------------------------------

test("findMemorialPos: the block above the feet, else squares around the feet from low to high", () => {
  const death = { x: 0, y: 64, z: 0 };
  assert.deepEqual(core.memorialPos(death, () => true, 2, 3), { x: 0, y: 65, z: 0 });
  const tried = [];
  assert.equal(core.memorialPos(death, (p) => { tried.push(p); return false; }, 2, 3), null);
  assert.deepEqual(tried[0], { x: 0, y: 65, z: 0 });
  // dy 0, radius 1: x fastest, then z (BlockPos$4#computeNext).
  assert.deepEqual(tried.slice(1, 4), [{ x: -1, y: 64, z: -1 }, { x: 0, y: 64, z: -1 }, { x: 1, y: 64, z: -1 }]);
  // 1 + per height (9 + 25), heights 0..3.
  assert.equal(tried.length, 1 + 4 * (9 + 25));
  assert.deepEqual(tried.at(-1), { x: 2, y: 67, z: 2 });
  const free = { x: 1, y: 64, z: 0 };
  assert.deepEqual(core.memorialPos(death, (p) => p.x === free.x && p.y === free.y && p.z === free.z, 2, 3), free);
});

test("a player's memorials, in the order they were made", () => {
  const records = [
    { uid: "b", type: mem.type, owner: "1", order: 5 },
    { uid: "a", type: mem.type, owner: "1", order: 2 },
    { uid: "c", type: mem.type, owner: "2", order: 1 },
    { uid: "d", type: "waystones:waystone", owner: "1", order: 0 },
  ];
  assert.deepEqual(core.memorialTargets(records, mem.type, "1").map((r) => r.uid), ["a", "b"]);
});

// -- dying with an epitaph ------------------------------------------------------

test("dying with an epitaph leaves a memorial above the feet, facing the player, and uses up the epitaph", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(EPITAPH, 1), location: DEATH, yaw: 0 });
  die(alex);
  const block = overworld.blockAt(ABOVE);
  assert.equal(block.typeId, MEMORIAL);
  // Looking south (yaw 0): fromYRot is SOUTH, turned round: north.
  assert.equal(block.permutation.getState("minecraft:cardinal_direction"), "north");
  const stored = record(overworld, ABOVE);
  assert.equal(stored.type, mem.type);
  assert.equal(stored.owner, alex.id);
  assert.equal(stored.facing, "north");
  assert.deepEqual(stored.name, NAME);
  assert.equal(stored.origin, "PLAYER");
  assert.equal(alex.slots[0], undefined);
  assert.deepEqual(alex.heard, [{ id: "random.totem", volume: 1.0, pitch: 1.0 }]);
});

test("the epitaph is found on the ground where the player died (Bedrock dropped the inventory)", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { location: DEATH, yaw: 90 });
  const near = dropItem(overworld, new ItemStack(EPITAPH, 1), { x: 21.2, y: 64.3, z: 30.1 });
  die(alex);
  assert.equal(overworld.blockAt(ABOVE).typeId, MEMORIAL);
  // yaw 90 looks west: the memorial faces east.
  assert.equal(overworld.blockAt(ABOVE).permutation.getState("minecraft:cardinal_direction"), "east");
  assert.equal(near.isValid, false);
});

test("an epitaph farther than the drop radius, or none at all, leaves nothing", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const far = dropItem(overworld, new ItemStack(EPITAPH, 1), { x: DEATH.x + mem.drop_radius + 1, y: 64, z: DEATH.z });
  const alex = makePlayer(overworld, { location: DEATH });
  die(alex);
  assert.equal(overworld.blockAt(ABOVE).typeId, "minecraft:air");
  assert.equal(far.isValid, true);
  assert.equal(alex.heard.length, 0);
});

test("the off hand counts; with no room nearby nothing happens and the epitaph stays", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { location: DEATH, offhand: new ItemStack(EPITAPH, 1) });
  die(alex);
  assert.equal(overworld.blockAt(ABOVE).typeId, MEMORIAL);
  assert.equal(alex.equipment.Offhand, undefined);
  // Buried: every block around is stone.
  clearWorld();
  const buried = makeDimension("minecraft:overworld");
  for (let x = 18; x <= 22; x++) {
    for (let y = 64; y <= 67; y++) {
      for (let z = 28; z <= 32; z++) buried.set({ x, y, z }, "minecraft:stone");
    }
  }
  const sam = makePlayer(buried, { held: new ItemStack(EPITAPH, 1), location: DEATH });
  die(sam);
  assert.equal(sam.slots[0].typeId, EPITAPH);
  assert.equal(sam.heard.length, 0);
});

test("a block above the feet that is taken moves the memorial to the first free block around the feet", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  overworld.set(ABOVE, "minecraft:stone");
  overworld.set({ x: 19, y: 64, z: 29 }, "minecraft:stone");
  dieWithEpitaph(overworld, DEATH);
  // dy 0, radius 1, the square's first block (x 19, z 29) is taken: the next.
  assert.equal(overworld.blockAt({ x: 20, y: 64, z: 29 }).typeId, MEMORIAL);
});

// -- the memorial in menus ----------------------------------------------------------

test("a memorial tops its owner's waystone menu with an Epitaph line; choosing it is free and removes it", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { location: { x: 100.5, y: 64, z: 2.5 } });
  const from = place(overworld, W, WAYSTONE, "Home", alex);
  place(overworld, { x: 140, y: 64, z: 0 }, WAYSTONE, "Farm", alex);
  const ghost = dieWithEpitaph(overworld, DEATH);
  // The memorial is the dead player's; make it Alex's for this menu.
  const stored = record(overworld, ABOVE);
  stored.owner = alex.id;
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, ABOVE), JSON.stringify(stored));
  assert.ok(ghost);
  _respond({ canceled: false, selection: 0 });
  interact(overworld, W, alex);
  _flush();
  await settle();
  const form = _shown.at(-1);
  assert.equal(form.buttons.length, 2);
  const label = form.buttons[0].text.rawtext;
  assert.deepEqual(label[0], NAME);
  // Free: no xp line; the requirement line in LIGHT_PURPLE.
  assert.deepEqual(label.slice(1), [{ text: "\n" }, { text: "\u00a7d" },
    { translate: table.messages.epitaph_requirement, with: { rawtext: [{ translate: table.messages.epitaph }] } }]);
  assert.equal(form.buttons[1].text.rawtext[0].text, "Farm");
  assert.equal(alex.xp, 0);
  // Beside the memorial (facing north: its north side), and it is gone.
  assert.deepEqual(alex.location, { x: 20.5, y: 65.5, z: 29.5 });
  assert.equal(record(overworld, ABOVE), undefined);
  assert.ok(overworld.commands.includes("setblock 20 65 30 air destroy"));
  assert.equal(overworld.blockAt(ABOVE).typeId, "minecraft:air");
  assert.ok(from);
});

test("another player's memorial is not listed, nor is any in a portstone's menu", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { location: { x: 100.5, y: 64, z: 2.5 } });
  place(overworld, W, WAYSTONE, "Home", alex);
  place(overworld, { x: 140, y: 64, z: 0 }, WAYSTONE, "Farm", alex);
  dieWithEpitaph(overworld, DEATH);
  interact(overworld, W, alex);
  _flush();
  await settle();
  assert.deepEqual(_shown.at(-1).buttons.map((b) => b.text.rawtext[0].text), ["Farm"]);
  if (!PORTSTONE) return;
  const mine = dieWithEpitaph(overworld, { x: 40.5, y: 64, z: 40.5 });
  const stored = record(overworld, { x: 40, y: 65, z: 40 });
  stored.owner = alex.id;
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, stored.pos), JSON.stringify(stored));
  const P = { x: 0, y: 64, z: 5 };
  overworld.set(P, PORTSTONE, { [HALF]: "lower", "minecraft:cardinal_direction": "north" });
  interact(overworld, P, alex);
  _flush();
  await settle();
  assert.ok(mine);
  assert.ok(_shown.at(-1).buttons.every((b) => b.text.rawtext[0].translate !== table.messages.memorial_name));
});

test("a memorial lists in a sharestone's menu too", async () => {
  if (!SHARESTONE) return;
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { location: { x: 100.5, y: 64, z: 2.5 } });
  place(overworld, W, SHARESTONE, "Here");
  const ghost = dieWithEpitaph(overworld, DEATH);
  const stored = record(overworld, ABOVE);
  stored.owner = alex.id;
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, ABOVE), JSON.stringify(stored));
  interact(overworld, W, alex);
  _flush();
  await settle();
  assert.ok(ghost);
  assert.deepEqual(_shown.at(-1).buttons[0].text.rawtext[0], NAME);
});

test("a memorial whose block is gone says so and is forgotten", async () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { location: { x: 100.5, y: 64, z: 2.5 } });
  place(overworld, W, WAYSTONE, "Home", alex);
  const ghost = dieWithEpitaph(overworld, DEATH);
  const stored = record(overworld, ABOVE);
  stored.owner = alex.id;
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, ABOVE), JSON.stringify(stored));
  overworld.set(ABOVE, "minecraft:stone");
  _respond({ canceled: false, selection: 0 });
  interact(overworld, W, alex);
  _flush();
  await settle();
  assert.ok(ghost);
  assert.equal(alex.teleports.length, 0);
  assert.deepEqual(alex.actionbar.at(-1), { rawtext: [{ translate: table.messages.missing }] });
  assert.equal(record(overworld, ABOVE), undefined);
});

test("using a memorial does nothing; breaking it forgets it", () => {
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  dieWithEpitaph(overworld, DEATH);
  const alex = makePlayer(overworld, { location: { x: 20.5, y: 64, z: 28.5 } });
  alex.isSneaking = true;
  interact(overworld, ABOVE, alex);
  alex.isSneaking = false;
  interact(overworld, ABOVE, alex);
  _flush();
  assert.equal(_shown.length, 0);
  assert.equal(alex.chat.length + alex.actionbar.length, 0);
  const permutation = overworld.blockAt(ABOVE).permutation;
  overworld.set(ABOVE, "minecraft:air");
  component.onPlayerBreak({ block: overworld.blockAt(ABOVE), brokenBlockPermutation: permutation, dimension: overworld,
    player: alex });
  assert.equal(record(overworld, ABOVE), undefined);
});

// -- item menus, bound scrolls and portals ------------------------------------------------

function mine(overworld, alex, location = DEATH) {
  const ghost = dieWithEpitaph(overworld, location);
  const pos = core.blockOf({ ...location, y: location.y + 1 });
  const stored = record(overworld, pos);
  stored.owner = alex.id;
  world.setDynamicProperty(core.recordKey("waystones", overworld.id, pos), JSON.stringify(stored));
  assert.ok(ghost);
  return pos;
}

async function hold(player, ticks) {
  _fire("after", "itemUse", { source: player, itemStack: player.slots[player.selectedSlotIndex] });
  for (let i = 0; i < ticks; i++) _runIntervals();
  _flush();
  await settle();
}

test("the warp scroll's and warp stone's menus list the memorial first; going there removes it", async () => {
  const scroll = table.scrolls && Object.keys(table.scrolls.items).find((id) => table.scrolls.items[id].kind === "warp");
  const stone = table.warp_stones && Object.keys(table.warp_stones.items)[0];
  for (const item of [scroll, stone].filter(Boolean)) {
    clearWorld();
    const overworld = makeDimension("minecraft:overworld");
    const alex = makePlayer(overworld, { held: new ItemStack(item, 1) });
    place(overworld, W, WAYSTONE, "Home", alex);
    const pos = mine(overworld, alex);
    _respond({ canceled: false, selection: 0 });
    await hold(alex, item === stone ? table.warp_stones.use_time : table.scrolls.use_time);
    const form = _shown.at(-1);
    assert.deepEqual(form.buttons[0].text.rawtext[0], NAME, item);
    assert.equal(form.buttons[1].text.rawtext[0].text, "Home", item);
    assert.deepEqual(alex.location, { x: 20.5, y: 65.5, z: 29.5 }, item);
    assert.equal(record(overworld, pos), undefined, item);
    assert.equal(alex.xp, 0, item);
  }
});

/** A standing warp portal at `pos` (facing north) that `player` last came through. */
function returnPortalFor(dimension, player, pos = { x: 0, y: 64, z: 3 }) {
  const portal = table.warp_portals.blocks[0];
  dimension.set(pos, portal, { [HALF]: "lower", "minecraft:cardinal_direction": "north" });
  dimension.set({ ...pos, y: pos.y + 1 }, portal, { [HALF]: "upper", "minecraft:cardinal_direction": "north" });
  world.setDynamicProperty(core.recordKey("waystones", dimension.id, pos), JSON.stringify({ uid: "portal1",
    type: table.warp_portals.type, dimension: dimension.id, pos, facing: "north", target: null, age: 0,
    name: { translate: table.messages.return_to_portal } }));
  player.setDynamicProperty(table.warp_portals.return_property, "portal1");
}

const RETURN = () => ({ translate: table.messages.return_to_portal });

test("Return to Portal is pinned to the top with the memorials, after them: waystone, warp scroll, warp stone", async () => {
  if (!table.warp_portals) return;
  // WaystoneSelectionScreenBase#pinReturnPortalFirst L447-450: a warp portal
  // and a fleeting memorial both sort first; between them the default
  // MANUAL order, memorials (L313 / L295) before the return portal (L318 / L302).
  const scroll = table.scrolls && Object.keys(table.scrolls.items).find((id) => table.scrolls.items[id].kind === "warp");
  const stone = table.warp_stones && Object.keys(table.warp_stones.items)[0];
  for (const item of [null, scroll, stone].filter((i) => i !== undefined)) {
    clearWorld();
    const overworld = makeDimension("minecraft:overworld");
    const alex = makePlayer(overworld, { held: item ? new ItemStack(item, 1) : undefined, xp: 100,
      location: { x: 100.5, y: 64, z: 2.5 } });
    place(overworld, W, WAYSTONE, "Home", alex);
    place(overworld, { x: 140, y: 64, z: 0 }, WAYSTONE, "Farm", alex);
    const pos = mine(overworld, alex);
    returnPortalFor(overworld, alex);
    _respond({ canceled: false, selection: 1 });
    if (item) {
      await hold(alex, item === stone ? table.warp_stones.use_time : table.scrolls.use_time);
    } else {
      interact(overworld, W, alex);
      _flush();
      await settle();
    }
    const labels = _shown.at(-1).buttons.map((b) => b.text.rawtext[0]);
    const rest = item ? [{ text: "Home" }, { text: "Farm" }] : [{ text: "Farm" }];
    assert.deepEqual(labels, [NAME, RETURN(), ...rest], item ?? "waystone");
    // The second entry is Return to Portal: beside the portal on its facing side.
    assert.deepEqual(alex.location, { x: 0.5, y: 64.5, z: 2.5 }, item ?? "waystone");
    assert.ok(record(overworld, pos), item ?? "waystone"); // the memorial is still there
  }
});

test("a blank scroll binds to a memorial, and the bound scroll's teleport removes it", async () => {
  if (!table.scrolls || !table.scrolls.bound) return;
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(table.scrolls.blank[0], 2), location: { x: 20.5, y: 64, z: 28.5 } });
  place(overworld, W, WAYSTONE, "Home", alex);
  const pos = mine(overworld, alex);
  interact(overworld, pos, alex);
  const bound = alex.slots.find((s) => s && s.typeId === table.scrolls.bound);
  assert.ok(bound);
  assert.equal(bound.getDynamicProperty(table.scrolls.binding_property), record(overworld, pos).uid);
  assert.deepEqual(bound.getLore(), []); // its name is a translation key, which lore can't carry
  alex.selectedSlotIndex = alex.slots.indexOf(bound);
  alex.location = { x: 0.5, y: 64, z: 0.5 };
  await hold(alex, table.scrolls.use_time);
  assert.deepEqual(alex.location, { x: 20.5, y: 65.5, z: 29.5 });
  assert.equal(record(overworld, pos), undefined);
  assert.equal(alex.slots[alex.selectedSlotIndex], undefined);
});

test("a portal opened to a memorial: the first through removes it, the next closes the portal", async () => {
  if (!table.warp_portals) return;
  clearWorld();
  const overworld = makeDimension("minecraft:overworld");
  const alex = makePlayer(overworld, { held: new ItemStack(table.warp_portals.scroll.items[0], 1) });
  place(overworld, W, WAYSTONE, "Home", alex);
  const pos = mine(overworld, alex);
  _respond({ canceled: false, selection: 0 });
  await hold(alex, table.warp_portals.scroll.use_time);
  assert.deepEqual(_shown.at(-1).buttons[0].text.rawtext[0], NAME);
  const P = { x: 0, y: 64, z: 3 };
  const PORTAL = table.warp_portals.blocks[0];
  assert.equal(overworld.blockAt(P).typeId, PORTAL);
  // Alex walks in.
  alex.location = { x: 0.5, y: 64, z: 3.5 };
  portalComponent.onTick({ block: overworld.blockAt(P), dimension: overworld });
  assert.deepEqual(alex.location, { x: 20.5, y: 65.5, z: 29.5 });
  assert.equal(record(overworld, pos), undefined);
  // A second player follows: the target is gone, the portal closes.
  const sam = makePlayer(overworld, { location: { x: 0.5, y: 64, z: 3.5 } });
  portalComponent.onTick({ block: overworld.blockAt(P), dimension: overworld });
  assert.equal(sam.teleports.length, 0);
  assert.deepEqual(sam.chat.at(-1), { rawtext: [{ translate: table.messages.attunement_lost }] });
  assert.equal(overworld.blockAt(P).typeId, "minecraft:air");
  assert.ok(BESIDE_W);
  assert.deepEqual(error("x").rawtext[0], { text: "\u00a74" });
});
