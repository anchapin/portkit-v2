// A minimal stand-in for @minecraft/server: just what the cutting board runtime
// touches, recording what it did so tests can check it. Not the real API.

export const EquipmentSlot = { Mainhand: "Mainhand", Offhand: "Offhand" };
export const GameMode = { Creative: "Creative", Survival: "Survival" };

const BLOCK_ITEMS = new Set(["minecraft:gravel", "minecraft:acacia_log", "minecraft:oak_door"]);
export const BlockTypes = { get: (id) => (BLOCK_ITEMS.has(id) ? { id } : undefined) };
export const EnchantmentTypes = { get: (id) => ({ id }) };

const MAX = {
  "minecraft:iron_shovel": 1, "farmersdelight:iron_knife": 1, "minecraft:wooden_shovel": 1,
  // The warp plate's shards (AttunedShardItem stacksTo(1), CrumblingAttunedShardItem stacksTo(4)).
  "waystones:attuned_shard": 1, "waystones:crumbling_attuned_shard": 4,
};
const DURABILITY = { "minecraft:iron_shovel": 250, "farmersdelight:iron_knife": 250, "minecraft:wooden_shovel": 59 };

export class ItemStack {
  constructor(typeId, amount = 1) {
    this.typeId = typeId;
    this.maxAmount = MAX[typeId] ?? 64;
    if (amount > this.maxAmount) throw new Error(`amount ${amount} > max ${this.maxAmount} for ${typeId}`);
    this.amount = amount;
    this.nameTag = undefined;
    this._lore = [];
    this._tags = [];
    this._enchantments = [];
    this._durability = DURABILITY[typeId] ? { damage: 0, maxDurability: DURABILITY[typeId] } : undefined;
  }
  getLore() { return [...this._lore]; }
  // Like Bedrock: dynamic properties only on non-stackable items.
  getDynamicProperty(key) { return (this._props ?? {})[key]; }
  setDynamicProperty(key, value) {
    if (this.maxAmount > 1) throw new Error(`UnsupportedFunctionalityError: ${this.typeId} is stackable`);
    this._props = { ...(this._props ?? {}), [key]: value };
  }
  setLore(lore) { this._lore = [...lore]; }
  hasTag(tag) { return this._tags.includes(tag); }
  isStackableWith(other) {
    return other.typeId === this.typeId && this.maxAmount > 1 && (other.nameTag ?? "") === (this.nameTag ?? "");
  }
  getComponent(id) {
    if (id === "minecraft:durability") return this._durability;
    if (id === "minecraft:enchantable") {
      const list = this._enchantments;
      return {
        getEnchantments: () => list.map((e) => ({ type: { id: e.id }, level: e.level })),
        getEnchantment: (name) => {
          const found = list.find((e) => e.id === name);
          return found ? { type: { id: name }, level: found.level } : undefined;
        },
        addEnchantment: (e) => list.push({ id: e.type.id, level: e.level }),
      };
    }
    return undefined;
  }
}

const properties = new Map();
// World events a runtime subscribes to (skillet: itemUse, entityHitEntity),
// by name; tests fire them through _fire.
const subscribed = { before: {}, after: {} };
function events(side) {
  return new Proxy({}, {
    get: (_, name) => ({ subscribe: (fn) => { (subscribed[side][name] ??= []).push(fn); return fn; } }),
  });
}
const players = [];
const dimensions = new Map();
export const world = {
  getDynamicProperty: (key) => properties.get(key),
  getDynamicPropertyIds: () => [...properties.keys()],
  getDimension: (id) => dimensions.get(id),
  _dimensions: dimensions,
  setDynamicProperty: (key, value) => (value === undefined ? properties.delete(key) : properties.set(key, value)),
  _properties: properties,
  beforeEvents: events("before"),
  afterEvents: events("after"),
  getPlayers: () => [...players],
  _players: players,
};

/** Fire a subscribed world event ("before" | "after", name) with `event`. */
export function _fire(side, name, event) {
  for (const fn of subscribed[side][name] ?? []) fn(event);
  return event;
}

const startup = [];
// system.run callbacks wait in _queue until a test calls _flush(); intervals
// are kept with their period and run by _runIntervals().
const queue = [];
const intervals = [];
export const system = {
  beforeEvents: { startup: { subscribe: (fn) => startup.push(fn) } },
  run: (fn) => { queue.push(fn); return queue.length; },
  runInterval: (fn, period) => { intervals.push({ fn, period }); return intervals.length; },
};

/** Run every queued system.run callback. */
export function _flush() {
  while (queue.length) queue.shift()();
}

/** Run every registered interval once; returns their periods. */
export function _runIntervals() {
  for (const { fn } of intervals) fn();
  return intervals.map((i) => i.period);
}

/** Run startup and return {componentId: component} as registered. */
export function _startup() {
  const registered = {};
  for (const fn of startup) {
    fn({ blockComponentRegistry: { registerCustomComponent: (id, c) => { registered[id] = c; } } });
  }
  return registered;
}

export function _dimension() {
  return {
    id: "minecraft:overworld",
    sounds: [],
    spawned: [],
    entities: [],
    commands: [],
    getEntities() { return this.entities; },
    runCommand(command) { this.commands.push(command); return { successCount: 1 }; },
    playSound(id, location, options) { this.sounds.push({ id, location, ...options }); },
    spawnItem(stack, location) {
      const entity = { stack, location, impulses: [], clearVelocity() {}, applyImpulse(v) { this.impulses.push(v); } };
      this.spawned.push(entity);
      return entity;
    },
  };
}

export function _player(dimension, held, { creative = false, inventoryRoom = 1000 } = {}) {
  const slots = { Mainhand: held };
  const inventory = [];
  const player = {
    dimension,
    location: { x: 0, y: 64, z: 0 },
    isSneaking: false,
    experience: 0,
    addExperience(n) { this.experience += n; return this.experience; },
    actionbar: [],
    inventory,
    getGameMode: () => (creative ? GameMode.Creative : GameMode.Survival),
    onScreenDisplay: { setActionBar: (m) => player.actionbar.push(m) },
    getComponent(id) {
      if (id === "minecraft:equippable") {
        return { getEquipment: (s) => slots[s], setEquipment: (s, v) => { slots[s] = v; } };
      }
      if (id === "minecraft:inventory") {
        return {
          container: {
            addItem: (stack) => {
              if (inventoryRoom >= stack.amount) { inventory.push(stack); return undefined; }
              const left = new ItemStack(stack.typeId, stack.amount - inventoryRoom);
              if (inventoryRoom > 0) inventory.push(new ItemStack(stack.typeId, inventoryRoom));
              return left;
            },
          },
        };
      }
      return undefined;
    },
    get held() { return slots.Mainhand; },
  };
  return player;
}

export function _block(dimension, facing = "north", location = { x: 10, y: 64, z: -3 }) {
  return { dimension, location, permutation: { getState: (s) => (s === "minecraft:cardinal_direction" ? facing : undefined) } };
}

// -- cooking pot additions ------------------------------------------------------

export const Direction = { Down: "Down", Up: "Up", North: "North", South: "South", East: "East", West: "West" };

/** A permutation: a block type id plus states, with withState like Bedrock's. */
export function _permutation(typeId, states = {}) {
  return {
    type: { id: typeId },
    states: { ...states },
    getState(name) { return this.states[name]; },
    withState(name, value) { return _permutation(typeId, { ...this.states, [name]: value }); },
  };
}

/** BlockPermutation.resolve, as the warp portal sets its halves. */
export const BlockPermutation = { resolve: (typeId, states = {}) => _permutation(typeId, states) };

/**
 * A placed block whose neighbours below are `below` ([{ id, states }] from the
 * block under it downward). setPermutation records the change.
 */
export function _potBlock(dimension, { typeId = "farmersdelight:cooking_pot", facing = "north", support = "none",
  below = [], location = { x: 4, y: 70, z: 8 } } = {}) {
  const block = {
    dimension,
    location,
    typeId,
    permutation: _permutation(typeId, { "minecraft:cardinal_direction": facing, "farmersdelight:support": support }),
    setPermutation(p) { this.permutation = p; },
  };
  block.below = (steps = 1) => {
    const entry = below[steps - 1];
    if (!entry) return { typeId: "minecraft:air", permutation: _permutation("minecraft:air") };
    return { typeId: entry.id, permutation: _permutation(entry.id, entry.states ?? {}) };
  };
  return block;
}

// -- stove additions ------------------------------------------------------------

export const EntityDamageCause = { campfire: "campfire", fire: "fire" };

/**
 * A placed stove: `lit` is the custom state's string value; `above` is the
 * block on top ({ isAir, isLiquid }, air by default); `entities` are what
 * dimension.getEntities returns near it.
 */
export function _stoveBlock(dimension, { typeId = "farmersdelight:stove", facing = "north", lit = "true",
  above = { isAir: true, isLiquid: false }, location = { x: 2, y: 64, z: 5 } } = {}) {
  const block = {
    dimension,
    location,
    typeId,
    above: () => above,
    permutation: _permutation(typeId, { "minecraft:cardinal_direction": facing, "farmersdelight:lit": lit }),
    setPermutation(p) { this.permutation = p; },
    setAbove(next) { above = next; },
  };
  return block;
}

/** An entity standing somewhere, recording the damage it takes. */
export function _entity(location, { typeId = "minecraft:zombie", living = true, sneaking = false, onGround = true,
  inanimate = false } = {}) {
  return {
    typeId,
    location,
    isSneaking: sneaking,
    isOnGround: onGround,
    damage: [],
    getComponent(id) { return id === "minecraft:health" && (living || inanimate) ? { currentValue: 20 } : undefined; },
    matches(options) { return !!inanimate && (options.families || []).includes("inanimate"); },
    applyDamage(amount, options) { this.damage.push({ amount, ...options }); return true; },
  };
}
