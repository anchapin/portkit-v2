// portkit station runtime: Farmer's Delight skillet, pure logic (#177).
//
// Fixed file, copied verbatim into every pack that ships the skillet
// (portkit/runtime/; see docs/decisions.md). It imports nothing, so node can
// test it offline (tests/js/). The recipe data lives in the generated table
// (scripts/portkit/data/<namespace>_skillet.js); the Bedrock side is skillet.js.
//
// Behaviour is Farmer's Delight's own, read from its source at the versions
// the converter accepts: vectorwing/FarmersDelight dd8b9b0b (NeoForge 1.3.4)
// and MehVahdJukaar/FarmersDelightRefabricated a8cb49ed (Fabric 3.6.28).
// "Block" below is common/block/SkilletBlock.java, "BE"
// common/block/entity/SkilletBlockEntity.java, "Item"
// common/item/SkilletItem.java, NeoForge line numbers (the Refabricated logic
// is the same; its lines are in the data table's header).
//
// The placed skillet, as stored: the skillet item it was placed from (BE
// skilletStack, for its Fire Aspect level and to drop it again), one stack
// being cooked (BE inventory, one slot), and the cooking counters (BE
// cookingTime / cookingTimeTotal).

export function emptySkillet(item = null) {
  return { item, stack: null, cookTime: 0, cookTimeTotal: 0 };
}

/**
 * Block#getSkilletCookingTime (L199-216): the recipe's time (600 when it has
 * none), divided by 5 and shortened by 5 points per Fire Aspect level, whole
 * seconds only, at least 3 seconds (MINIMUM_COOKING_TIME, 60 ticks) and never
 * more than the recipe's own time. Java does the reduction in float
 * (0.2F - level * 0.05 assigned back to a float), so Math.fround here.
 */
export function cookingTime(original, fireAspect, rule) {
  const base = original > 0 ? original : rule.default_cooking_time;
  const seconds = Math.trunc(base / 20);
  let reduction = Math.fround(rule.reduction);
  if (fireAspect > 0) reduction = Math.fround(reduction - fireAspect * rule.fire_aspect_step);
  const result = Math.trunc(Math.fround(seconds * reduction)) * 20;
  // Mth.clamp(value, min, max): every recipe the table holds takes at least
  // min ticks (the converter leaves out shorter ones), so min <= max here.
  return Math.min(Math.max(result, rule.min_cooking_time), original);
}

/** The Fire Aspect level of a stored item ({ enchantments: [{ id, level }] }). */
export function fireAspectOf(stored) {
  const found = ((stored && stored.enchantments) || []).find((e) => e.id === "fire_aspect" || e.id === "minecraft:fire_aspect");
  return found ? found.level : 0;
}

/** The campfire recipe for an item, or undefined (the table has at most one per item). */
export function findRecipe(recipes, id) {
  return recipes.find((r) => r.ingredient.includes(id));
}

/** Facing.getClockWise(): where a cooked item is thrown (BE L100). */
const CLOCKWISE = { north: [1, 0], east: [0, 1], south: [-1, 0], west: [0, -1] };

/**
 * BE#cookAndOutputItems (L101-103): the result appears at the block's centre,
 * 0.3 up, moving 0.08 toward the side clockwise of the facing and 0.25 up.
 */
export function launch(facing, rule) {
  const [x, z] = CLOCKWISE[facing] ?? CLOCKWISE.north;
  return { dx: 0.5, dy: rule.dy, dz: 0.5, vx: x * rule.speed, vy: rule.up, vz: z * rule.speed };
}

/**
 * What using the placed skillet with `heldId` does (Block#useItemOn L73-97,
 * BE#addItemToCook L158-179): "take" with an empty hand, "insert" a food a
 * campfire recipe takes when the skillet is empty, otherwise "invalid"
 * (NeoForge shows block.farmersdelight.skillet.invalid_item; Refabricated
 * only calls addItemToCook for an empty skillet and a campfire input, so the
 * table's message is null there and nothing happens).
 */
export function interaction(skillet, heldId, recipes) {
  if (!heldId) return "take";
  if (!skillet.stack && findRecipe(recipes, heldId)) return "insert";
  return "invalid";
}

/**
 * BE#addItemToCook (L165-169): the whole held stack goes in, up to the most
 * one slot holds (ItemStackHandler: 64, or the item's own stack size); the
 * cooking time is the skillet's for that recipe and the counter restarts.
 * Returns how many went in.
 */
export function insert(skillet, stored, amount, max, recipe, rule) {
  const moved = Math.min(amount, max);
  if (moved <= 0) return 0;
  skillet.stack = { ...stored, amount: moved };
  skillet.cookTimeTotal = cookingTime(recipe.cookingtime, fireAspectOf(skillet.item), rule);
  skillet.cookTime = 0;
  return moved;
}

/** BE#removeItem (L181-183): the whole stored stack comes out. */
export function takeOut(skillet) {
  const stack = skillet.stack;
  skillet.stack = null;
  return stack;
}

/**
 * BE#cookingTick (L51-69) run `interval` times. Heated: an empty skillet
 * resets its counter; otherwise the counter climbs and, at the total, one
 * item becomes the recipe's result (cookAndOutputItems L94-109). Not heated:
 * the counter falls by 2 per tick, never below 0. Returns { cooked: [stored
 * result], changed }.
 */
export function step(skillet, { heated, interval, recipes }) {
  const cooked = [];
  let changed = false;
  for (let t = 0; t < interval; t += 1) {
    if (heated) {
      if (!skillet.stack) {
        if (skillet.cookTime !== 0) changed = true;
        skillet.cookTime = 0;
        continue;
      }
      skillet.cookTime += 1;
      changed = true;
      if (skillet.cookTime >= skillet.cookTimeTotal) {
        const recipe = findRecipe(recipes, skillet.stack.id);
        if (recipe) {
          cooked.push({ id: recipe.result.item, amount: recipe.result.count });
          skillet.cookTime = 0;
          skillet.stack.amount -= 1;
          if (skillet.stack.amount <= 0) skillet.stack = null;
        }
      }
    } else if (skillet.cookTime > 0) {
      skillet.cookTime = Math.min(Math.max(skillet.cookTime - 2, 0), skillet.cookTimeTotal);
      changed = true;
    }
  }
  return { cooked, changed };
}

/** BE#isCooking (L111-113): heated with something in it. */
export function isCooking(skillet, heated) {
  return heated && !!skillet.stack;
}

/**
 * Item#isPlayerNearHeatSource (L128-139): on fire, or any block in the 3x3x3
 * around the player's block is a heat source (the tag alone: an unlit
 * campfire counts, unlike under a placed skillet). `blocks` are views
 * ({ id, state(name) }) of those 27 blocks.
 */
export function nearHeat(onFire, blocks, rules, matches) {
  if (onFire) return true;
  return blocks.some((b) => rules.some((r) => matches(r, b)));
}

/**
 * Item#use (L154-183) with the skillet in one hand and the food in the other:
 * one item of the food goes into the skillet and cooking starts; its length
 * is getUseDuration (L147-151), the recipe's time through the same rule as the
 * placed skillet, with the held skillet's Fire Aspect.
 */
export function startHeld(stored, recipe, fireAspect, rule) {
  return {
    ingredient: { ...stored, amount: 1 },
    recipe: recipe.id,
    total: cookingTime(recipe.cookingtime, fireAspect, rule),
    elapsed: 0,
  };
}

/**
 * One run of `interval` ticks of held cooking: "done" (finishUsingItem
 * L223-247: the result goes to the player) once the time is up, else
 * "cooking".
 */
export function stepHeld(session, interval) {
  session.elapsed += interval;
  return session.elapsed >= session.total ? "done" : "cooking";
}

/**
 * Chance that one run of `interval` ticks plays a sound Java plays with
 * `chancePerTick` each tick: the chance at least one of those ticks would.
 */
export function soundChance(chancePerTick, interval) {
  return 1 - Math.pow(1 - chancePerTick, interval);
}

/** A plain-text summary of the placed skillet for the action bar. */
export function status(skillet, heated) {
  const parts = [skillet.stack ? `${skillet.stack.amount} ${skillet.stack.id}` : "empty"];
  if (skillet.stack && skillet.cookTimeTotal > 0) {
    parts.push(`cooking ${Math.floor((100 * skillet.cookTime) / skillet.cookTimeTotal)}%`);
  }
  parts.push(heated ? "heated" : "not heated");
  return parts.join(" | ");
}

/** A plain-text summary of held cooking for the action bar. */
export function heldStatus(session) {
  const pct = Math.min(100, Math.floor((100 * session.elapsed) / session.total));
  return `skillet: ${session.ingredient.id} | cooking ${pct}%`;
}

/** The dynamic-property key holding the skillet at this position. */
export function storageKey(component, dimensionId, location) {
  return `${component}|${dimensionId}|${location.x},${location.y},${location.z}`;
}
