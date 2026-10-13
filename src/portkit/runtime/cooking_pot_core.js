// portkit station runtime: Farmer's Delight cooking pot, pure logic (#177).
//
// Fixed file, copied verbatim into every pack that ships the cooking pot
// (portkit/runtime/; see docs/decisions.md, 2026-10-13). It imports nothing,
// so node can test it offline (tests/js/). The recipe data lives in the
// generated table (scripts/portkit/data/<namespace>_cooking_pot.js); the
// Bedrock side is cooking_pot.js.
//
// Behaviour is Farmer's Delight's own, read from its source at the versions
// the converter accepts: vectorwing/FarmersDelight dd8b9b0b (NeoForge 1.3.4)
// and MehVahdJukaar/FarmersDelightRefabricated a8cb49ed (Fabric 3.6.28). "BE"
// below is common/block/entity/CookingPotBlockEntity.java, "Block"
// common/block/CookingPotBlock.java, "Menu" .../container/CookingPotMenu.java,
// NeoForge line numbers (the Refabricated logic is the same; its lines are in
// the data table's header).
//
// The pot, as stored: six ingredient slots, the container slot, the output
// slot, the meal (BE's MEAL_DISPLAY_SLOT), the meal's container, the cook
// timer and the recipes used since experience was last paid out. A stored
// stack is { id, amount, ...item data }.

export const INPUT_SLOTS = 6;

export function emptyPot() {
  return {
    slots: [null, null, null, null, null, null],
    container: null,
    output: null,
    meal: null,
    mealContainer: null,
    cookTime: 0,
    cookTimeTotal: 0,
    used: {},
  };
}

/** Whether the pot holds nothing and isn't counting, so storage can be cleared. */
export function isIdle(pot) {
  return !hasInput(pot) && !pot.container && !pot.output && !pot.meal && pot.cookTime === 0
    && Object.keys(pot.used).length === 0;
}

/** BE#hasInput (L272-277): any ingredient slot holds something. */
export function hasInput(pot) {
  return pot.slots.some((s) => s && s.amount > 0);
}

/**
 * Whether `recipe` matches the ingredient slots. CookingPotRecipe#matches
 * (L100-112): the number of non-empty slots equals the number of ingredients,
 * and each ingredient takes its own slot (RecipeMatcher.findMatches; on
 * Refabricated StackedContents#canCraft) - one item per slot, whatever the
 * stack size.
 */
export function matches(recipe, ids) {
  if (ids.length !== recipe.ingredients.length) return false;
  const owner = new Array(ids.length).fill(-1); // slot -> ingredient
  const augment = (ingredient, seen) => {
    for (let slot = 0; slot < ids.length; slot++) {
      if (seen[slot] || !recipe.ingredients[ingredient].includes(ids[slot])) continue;
      seen[slot] = true;
      if (owner[slot] < 0 || augment(owner[slot], seen)) {
        owner[slot] = ingredient;
        return true;
      }
    }
    return false;
  };
  for (let i = 0; i < recipe.ingredients.length; i++) {
    if (!augment(i, new Array(ids.length).fill(false))) return false;
  }
  return true;
}

/**
 * The recipe the pot's contents make, or undefined. BE#getMatchingRecipe
 * (L261-264). The converter leaves out recipes that can match the same
 * contents, so at most one matches and Java's recipe-manager order never
 * matters.
 */
export function findRecipe(recipes, pot) {
  if (!hasInput(pot)) return undefined;
  const ids = pot.slots.filter((s) => s && s.amount > 0).map((s) => s.id);
  return recipes.find((r) => matches(r, ids));
}

/**
 * BE#canCook (L279-301): the result goes into an empty meal slot, or onto the
 * same meal while the slot's limit allows: Math.max(64, max stack size)
 * (the meal slot's getStackLimit, L524-529).
 */
export function canCook(recipe, meal, resultMax) {
  if (!meal) return true;
  if (meal.id !== recipe.result.item) return false;
  return meal.amount + recipe.result.count <= Math.max(64, resultMax);
}

/** BE#getContainer (L266-270): what a portion of the meal is served into. */
export function getContainer(pot) {
  return pot.meal && pot.mealContainer ? pot.mealContainer : null;
}

/** BE#isContainerValid (L456-460): the held item is the meal's container. */
export function isContainerValid(pot, id) {
  return !!id && !!pot.mealContainer && id === pot.mealContainer;
}

const COUNTER_CLOCKWISE = { north: "west", west: "south", south: "east", east: "north" };
const STEP = { north: [0, -1], south: [0, 1], west: [-1, 0], east: [1, 0] };

/**
 * Where an ingredient's leftover appears and how it moves.
 * BE#ejectIngredientRemainder (L336-343): 0.25 blocks from the centre toward
 * the pot's facing turned counter-clockwise, 0.7 up, moving 0.08 that way and
 * 0.25 up.
 */
export function ejectOffset(facing) {
  const [x, z] = STEP[COUNTER_CLOCKWISE[facing] ?? "west"];
  return { dx: x * 0.25, dy: 0.7, dz: z * 0.25, vx: x * 0.08, vy: 0.25, vz: z * 0.08 };
}

/**
 * One run of the pot's tick, standing for `interval` game ticks of
 * BE#cookingTick (L209-238). Returns what the binding must do:
 * { changed, cooked, ejected: [item ids to eject] }.
 *
 * - heated with ingredients: a matching recipe that canCook advances the timer
 *   (processCooking, L303-334); it finishes once the timer reaches the
 *   recipe's cookingtime, and then the meal grows by the result, the meal's
 *   container becomes the recipe's, the recipe is counted for experience and
 *   each ingredient slot gives up one item, ejecting its remainder;
 * - otherwise the timer falls by 2 a tick, down to 0;
 * - then a meal with no container moves to the output slot (moveMealToOutput,
 *   L412-422), and a meal with one is served into the stored containers
 *   (useStoredContainersOnMeal, L424-441).
 *
 * Java finishes at most one cook per tick and resets the timer to 0 (not the
 * overshoot), so a run of `interval` ticks finishes on the same tick count
 * whenever the cookingtime is a multiple of it.
 */
export function step(pot, ctx) {
  const { heated, recipes, interval, maxAmount, remainders } = ctx;
  const out = { changed: false, cooked: null, ejected: [] };
  let recipe;
  if (heated && hasInput(pot)) {
    recipe = findRecipe(recipes, pot);
    if (recipe && canCook(recipe, pot.meal, maxAmount(recipe.result.item))) {
      pot.cookTime += interval;
      pot.cookTimeTotal = recipe.cookingtime;
      if (pot.cookTime >= pot.cookTimeTotal) {
        pot.cookTime = 0;
        pot.mealContainer = recipe.container ?? null;
        if (!pot.meal) pot.meal = { id: recipe.result.item, amount: recipe.result.count };
        else pot.meal.amount += recipe.result.count;
        pot.used[recipe.id] = (pot.used[recipe.id] ?? 0) + 1;
        for (let i = 0; i < INPUT_SLOTS; i++) {
          const slot = pot.slots[i];
          if (!slot) continue;
          const left = remainders[slot.id];
          if (left) out.ejected.push(left);
          slot.amount -= 1;
          if (slot.amount <= 0) pot.slots[i] = null;
        }
        out.cooked = recipe;
        out.changed = true;
      }
    } else {
      decay(pot, interval);
    }
  } else if (pot.cookTime > 0) {
    decay(pot, interval);
  }

  if (pot.meal && pot.meal.amount > 0) {
    if (!pot.mealContainer) {
      out.changed = moveMealToOutput(pot, maxAmount) || out.changed;
    } else if (pot.container) {
      out.changed = useStoredContainersOnMeal(pot, maxAmount) || out.changed;
    }
  }
  return out;
}

function decay(pot, interval) {
  pot.cookTime = Math.min(Math.max(pot.cookTime - 2 * interval, 0), pot.cookTimeTotal);
}

/** BE#moveMealToOutput (L412-422). */
export function moveMealToOutput(pot, maxAmount) {
  const meal = pot.meal;
  const max = maxAmount(meal.id);
  const outAmount = pot.output ? pot.output.amount : 0;
  const count = Math.min(meal.amount, max - outAmount);
  if (count <= 0) return false;
  if (!pot.output) {
    pot.output = { id: meal.id, amount: count };
  } else if (pot.output.id === meal.id && sameData(pot.output, { id: meal.id })) {
    pot.output.amount += count;
  } else {
    return false;
  }
  takeMeal(pot, count);
  return true;
}

/** BE#useStoredContainersOnMeal (L424-441). */
export function useStoredContainersOnMeal(pot, maxAmount) {
  const meal = pot.meal;
  const box = pot.container;
  if (!isContainerValid(pot, box.id)) return false;
  // Java: outputStack.getCount() < outputStack.getMaxStackSize(); an empty
  // output slot counts as 0 of 64.
  const outMax = pot.output ? maxAmount(pot.output.id) : 64;
  const outAmount = pot.output ? pot.output.amount : 0;
  if (outAmount >= outMax) return false;
  const smaller = Math.min(meal.amount, box.amount);
  const count = Math.min(smaller, maxAmount(meal.id) - outAmount);
  if (count <= 0) return false;
  if (!pot.output) {
    pot.output = { id: meal.id, amount: count };
  } else if (pot.output.id === meal.id && sameData(pot.output, { id: meal.id })) {
    pot.output.amount += count;
  } else {
    return false;
  }
  box.amount -= count;
  if (box.amount <= 0) pot.container = null;
  takeMeal(pot, count);
  return true;
}

function takeMeal(pot, count) {
  pot.meal.amount -= count;
  if (pot.meal.amount <= 0) pot.meal = null;
}

/** Whether two stored stacks carry the same item data (name, lore, damage, enchantments). */
export function sameData(a, b) {
  const pick = (s) => JSON.stringify([s.nameTag ?? null, s.lore ?? null, s.damage ?? null, s.enchantments ?? null]);
  return a.id === b.id && pick(a) === pick(b);
}

/**
 * BE#useHeldItemOnMeal (L443-450), from Block#useItemOn (L80-86): a held
 * meal container with a meal in the pot serves one portion and uses one
 * container. Returns the served item id, or undefined.
 */
export function serve(pot, heldId) {
  if (!isContainerValid(pot, heldId) || !pot.meal) return undefined;
  const id = pot.meal.id;
  takeMeal(pot, 1);
  return id;
}

/**
 * Put a held stack in. Which slots: as shift-clicking it into the cooking pot
 * menu decides (Menu#quickMoveStack, L114-151), a serving container (the
 * farmersdelight:serving_containers tag) or the meal's container goes to the
 * container slot, anything else to the six ingredient slots.
 *
 * How: an ingredient stack goes whole into the first empty ingredient slot,
 * as placing it by hand into an empty menu slot does; only with no slot empty
 * does it go onto slots holding the same item. (Shift-click would merge it
 * onto a matching slot first, which would leave recipes that need the same
 * item in two slots - apple cider, hot cocoa, tomato sauce - uncookable by
 * hand.) The container slot fills like a shift-click: onto the same item, up
 * to its stack size. Returns how many moved. `stack` is the stored form of
 * the held stack; `max` its stack size.
 */
export function insert(pot, stack, max, servingContainers) {
  const toContainer = servingContainers.includes(stack.id) || stack.id === getContainer(pot);
  const indices = toContainer ? ["container"] : [0, 1, 2, 3, 4, 5];
  const get = (i) => (i === "container" ? pot.container : pot.slots[i]);
  const set = (i, v) => {
    if (i === "container") pot.container = v;
    else pot.slots[i] = v;
  };
  let left = stack.amount;
  const fillEmpty = () => {
    for (const i of indices) {
      if (get(i) || left <= 0) continue;
      const put = Math.min(left, max);
      set(i, { ...stack, amount: put });
      left -= put;
      return;
    }
  };
  const merge = () => {
    if (max <= 1) return;
    for (const i of indices) {
      const s = get(i);
      if (!s || !sameData(s, stack) || left <= 0) continue;
      const add = Math.min(left, max - s.amount);
      if (add > 0) {
        s.amount += add;
        left -= add;
      }
    }
  };
  if (toContainer) {
    merge();
    fillEmpty();
  } else {
    fillEmpty();
    merge();
  }
  return stack.amount - left;
}

/**
 * What an empty hand takes out (the runtime's stand-in for the menu): the
 * output slot (the menu's result slot, which also pays out experience),
 * else the last filled ingredient slot, else the container slot. Returns
 * { from, stack } and clears that slot, or undefined.
 */
export function takeOut(pot) {
  if (pot.output) {
    const stack = pot.output;
    pot.output = null;
    return { from: "output", stack };
  }
  for (let i = INPUT_SLOTS - 1; i >= 0; i--) {
    if (pot.slots[i]) {
      const stack = pot.slots[i];
      pot.slots[i] = null;
      return { from: "ingredient", stack };
    }
  }
  if (pot.container) {
    const stack = pot.container;
    pot.container = null;
    return { from: "container", stack };
  }
  return undefined;
}

/**
 * Experience owed for the recipes cooked since the last payout.
 * BE#splitAndSpawnExperience (L379-387), per recipe: floor(count x
 * experience), plus one with chance equal to the fraction left.
 */
export function experience(used, recipes, random) {
  let total = 0;
  for (const [id, count] of Object.entries(used)) {
    const recipe = recipes.find((r) => r.id === id);
    if (!recipe) continue;
    const xp = count * recipe.experience;
    let whole = Math.floor(xp);
    const fraction = xp - whole;
    if (fraction !== 0 && random() < fraction) whole += 1;
    total += whole;
  }
  return total;
}

/** Whether a block ({ id, state(name) }) matches one heat rule of the table. */
export function blockMatches(rule, block) {
  if (!block || block.id !== rule.id) return false;
  for (const [name, value] of Object.entries(rule.states ?? {})) {
    if (block.state(name) !== value) return false;
  }
  for (const [name, value] of Object.entries(rule.not ?? {})) {
    if (block.state(name) === value) return false;
  }
  return true;
}

/**
 * HeatableBlockEntity#isHeated (L19-38): the block below is a heat source
 * (lit, if it can be unlit), or a heat conductor with a heat source below it.
 */
export function isHeated(heat, below, belowTwo) {
  if (heat.sources.some((r) => blockMatches(r, below))) return true;
  if (heat.conductors.some((r) => blockMatches(r, below))) {
    return heat.sources.some((r) => blockMatches(r, belowTwo));
  }
  return false;
}

/** Block#getTrayState (L137-142): tray over a tray heat source, else none. */
export function trayState(heat, below) {
  return heat.tray.some((r) => blockMatches(r, below)) ? "tray" : "none";
}

/**
 * Chance that one run of `interval` ticks plays the boil sound, from Java's 1
 * in 10 per client tick (Block#animateTick, L176-188): the chance at least one
 * of those ticks would.
 */
export function boilChance(chancePerTick, interval) {
  return 1 - Math.pow(1 - chancePerTick, interval);
}

/** A plain-text summary of the pot for the action bar. */
export function status(pot, heated, recipe) {
  const parts = [];
  const inside = pot.slots.filter(Boolean).map((s) => `${s.amount} ${s.id}`);
  parts.push(inside.length ? inside.join(", ") : "empty");
  if (recipe && pot.cookTimeTotal > 0) {
    parts.push(`cooking ${Math.floor((100 * pot.cookTime) / pot.cookTimeTotal)}%`);
  }
  if (pot.meal) {
    parts.push(`meal: ${pot.meal.amount} ${pot.meal.id}${pot.mealContainer ? ` (serve with ${pot.mealContainer})` : ""}`);
  }
  if (pot.container) parts.push(`containers: ${pot.container.amount} ${pot.container.id}`);
  if (pot.output) parts.push(`ready: ${pot.output.amount} ${pot.output.id}`);
  parts.push(heated ? "heated" : "not heated");
  return parts.join(" | ");
}

/** The dynamic-property key holding the pot at this position. */
export function storageKey(component, dimensionId, location) {
  return `${component}|${dimensionId}|${location.x},${location.y},${location.z}`;
}
