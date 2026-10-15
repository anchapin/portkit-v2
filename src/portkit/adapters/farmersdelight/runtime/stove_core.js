// portkit station runtime: Farmer's Delight stove, pure logic (#177).
//
// Fixed file, copied verbatim into every pack that ships the stove
// (portkit/runtime/; see docs/decisions.md). It imports nothing, so node can
// test it offline (tests/js/). The recipe data lives in the generated table
// (scripts/portkit/data/<namespace>_stove.js); the Bedrock side is stove.js.
//
// Behaviour is Farmer's Delight's own, read from its source at the versions
// the converter accepts: vectorwing/FarmersDelight dd8b9b0b (NeoForge 1.3.4)
// and MehVahdJukaar/FarmersDelightRefabricated a8cb49ed (Fabric 3.6.28).
// "Block" below is common/block/AbstractStoveBlock.java, "BE"
// common/block/entity/AbstractStoveBlockEntity.java, NeoForge line numbers
// (the Refabricated logic is the same; its lines are in the data table's
// header).
//
// The stove, as stored: six spots on top, each holding one item (the
// handler's slot limit is 1, BE L223-231), with its cooking progress and the
// recipe's cooking time (BE cookingProgress / cookingTime). A stored item is
// { id, amount: 1, ...item data }.

export function emptyStove(slots = 6) {
  return {
    items: new Array(slots).fill(null),
    progress: new Array(slots).fill(0),
    total: new Array(slots).fill(0),
  };
}

/** BE#isEmpty (L191-193): no spot holds an item. */
export function isEmpty(stove) {
  return stove.items.every((s) => !s);
}

/**
 * The campfire recipe for an item, or undefined. BE#getCookingRecipe
 * (L152-155) asks the recipe manager for the first campfire_cooking recipe
 * taking it; the converter leaves out recipes that share an item, so at most
 * one matches and the manager's order never matters.
 */
export function findRecipe(recipes, id) {
  return recipes.find((r) => r.ingredient.includes(id));
}

/** BE#getNextEmptySlot (L157-162): the first free spot, or -1. */
export function nextEmptySlot(stove) {
  return stove.items.findIndex((s) => !s);
}

/**
 * BE#placeFood (L164-179): one item of the held stack onto the first free
 * spot, its cooking time the recipe's, its progress 0. Returns the spot, or
 * -1 when the stove is full (Java then consumes the click and does nothing).
 */
export function placeFood(stove, stored, recipe) {
  const slot = nextEmptySlot(stove);
  if (slot < 0) return -1;
  stove.items[slot] = { ...stored, amount: 1 };
  stove.total[slot] = recipe.cookingtime;
  stove.progress[slot] = 0;
  return slot;
}

/**
 * One run of the stove's tick, standing for `interval` game ticks of
 * BE#serverTick (L95-108). Returns { changed, cooked: [stored stacks to pop
 * out on top] }.
 *
 * - lit, cookAndOutputItems (L110-137): each occupied spot's progress grows;
 *   once it reaches the cooking time, the recipe's result (else the item
 *   itself, as Java's orElse(ingredient)) pops out and the spot empties;
 * - unlit, coolItems (L139-150): each progress falls by 2 a tick, clamped to
 *   0 .. the cooking time.
 *
 * Java finishes a spot on the first tick its progress reaches the cooking
 * time, so a run of `interval` ticks finishes on the same tick count whenever
 * the cooking time is a multiple of it (every corpus campfire recipe: 600).
 */
export function step(stove, { lit, interval, recipes }) {
  const cooked = [];
  let changed = false;
  if (isEmpty(stove)) return { changed, cooked };
  for (let i = 0; i < stove.items.length; i++) {
    if (lit) {
      const item = stove.items[i];
      if (!item) continue;
      changed = true;
      stove.progress[i] += interval;
      if (stove.progress[i] < stove.total[i]) continue;
      const recipe = findRecipe(recipes, item.id);
      cooked.push(recipe ? { id: recipe.result.item, amount: recipe.result.count } : { ...item });
      stove.items[i] = null;
    } else {
      if (stove.progress[i] <= 0) continue;
      changed = true;
      stove.progress[i] = Math.min(Math.max(stove.progress[i] - 2 * interval, 0), stove.total[i]);
    }
  }
  return { changed, cooked };
}

function holds(entry, id, hasTag) {
  if (!entry || !id) return false;
  if (Array.isArray(entry)) return entry.includes(id);
  return (entry.items || []).includes(id) || (entry.tags || []).some((t) => hasTag(t));
}

/**
 * What using `heldId` on the stove does. Block#useItemOn (L66-77): a lit
 * stove tries to put itself out (tryToExtinguish, L105-125: an item that can
 * shovel_dig, then a water bucket), an unlit one to light itself
 * (tryToIgnite, L79-103: flint and steel, then a fire charge); anything else
 * goes on to tryToPlaceFoodItem (L127-138), which needs a campfire recipe for
 * the item. Returns "extinguish_shovel" | "extinguish_water" | "ignite_flint"
 * | "ignite_charge" | "place" | null.
 */
export function interaction(table, lit, heldId, hasTag = () => false) {
  if (!heldId) return null;
  if (lit) {
    if (holds(table.extinguish.shovel, heldId, hasTag)) return "extinguish_shovel";
    if (Object.prototype.hasOwnProperty.call(table.extinguish.water, heldId)) return "extinguish_water";
  } else {
    if (holds(table.ignite.flint_and_steel, heldId, hasTag)) return "ignite_flint";
    if (holds(table.ignite.fire_charge, heldId, hasTag)) return "ignite_charge";
  }
  return findRecipe(table.recipes, heldId) ? "place" : null;
}

/**
 * Block#burnEntitySteppingOnStove (L180-186), called from stepOn for the
 * block an entity stands on: a lit stove hurts a living entity that isn't
 * stepping carefully (sneaking). `entity` is { living, sneaking, onGround,
 * feet: {x,y,z} } and `at` the stove's block position. Java also needs the
 * entity's box to overlap the grilling area (3..13 px across); every entity
 * at least 6 px wide standing over the stove's column does, so the feet's
 * column stands in for it.
 */
export function burns(lit, entity, at) {
  if (!lit || !entity.living || entity.sneaking || !entity.onGround) return false;
  const { x, y, z } = entity.feet;
  if (x < at.x || x >= at.x + 1 || z < at.z || z >= at.z + 1) return false;
  return y >= at.y + 1 - 0.01 && y <= at.y + 1 + 1 / 16;
}

/** The chance a sound Java rolls at `perTick` each tick plays at least once in `interval` ticks. */
export function soundChance(perTick, interval) {
  return 1 - Math.pow(1 - perTick, interval);
}

/** One standard normal draw (Box-Muller), for Java's nextGaussian. */
export function gaussian(random) {
  const u = Math.max(random(), Number.MIN_VALUE);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * random());
}

/**
 * Where a cooked item appears and how it moves. BE L128-130: the top centre
 * (x + 0.5, y + 1.0, z + 0.5), moving nextGaussian * 0.01 across and 0.1 up.
 */
export function cookedMotion(random) {
  return { dx: 0.5, dy: 1.0, dz: 0.5, vx: gaussian(random) * 0.01, vy: 0.1, vz: gaussian(random) * 0.01 };
}

/**
 * Whether a use costs the tool durability. Java's ItemStack#hurtAndBreak runs
 * vanilla Unbreaking: for an item that isn't armour each point of damage is
 * removed with chance level / (level + 1) (data/minecraft/enchantment/
 * unbreaking.json, 1.21.1). Creative players take no damage (the caller
 * checks that).
 */
export function takesDamage(unbreakingLevel, random) {
  if (unbreakingLevel <= 0) return true;
  return random() >= unbreakingLevel / (unbreakingLevel + 1);
}

/** The action-bar line: lit or not, what each spot holds and how far along it is. */
export function status(stove, lit, covered) {
  const parts = [lit ? "stove lit" : "stove unlit"];
  const cooking = [];
  stove.items.forEach((item, i) => {
    if (!item) return;
    const pct = stove.total[i] > 0 ? Math.min(100, Math.floor((100 * stove.progress[i]) / stove.total[i])) : 0;
    cooking.push(`${item.id} ${pct}%`);
  });
  parts.push(cooking.length ? `cooking: ${cooking.join(", ")}` : "nothing cooking");
  parts.push(`${stove.items.filter((s) => !s).length} free`);
  if (covered) parts.push("top covered");
  return parts.join(" | ");
}
