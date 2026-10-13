// portkit station runtime: Farmer's Delight cutting board, pure logic (#177).
//
// Fixed file, copied verbatim into every pack that ships the cutting board
// (portkit/runtime/; see docs/decisions.md, 2026-10-13). It imports nothing,
// so node can test it offline (tests/js/). The recipe data lives in the
// generated table (scripts/portkit/data/<namespace>_cutting_board.js); the
// Bedrock side is cutting_board.js.
//
// Behaviour is Farmer's Delight's own, read from its source at the versions
// the converter accepts: vectorwing/FarmersDelight dd8b9b0b (NeoForge 1.3.4)
// and MehVahdJukaar/FarmersDelightRefabricated a8cb49ed (Fabric 3.6.28).
// "BE" below is common/block/entity/CuttingBoardBlockEntity.java, "Block"
// common/block/CuttingBoardBlock.java, NeoForge line numbers.

/** Whether the tool may cut with this recipe: any listed item or Bedrock tag. */
export function toolMatches(tool, toolId, hasTag) {
  if (tool.items.includes(toolId)) return true;
  return tool.tags.some((tag) => hasTag(tag));
}

/**
 * The recipe for this stored item and tool, or undefined.
 * BE#getMatchingRecipe (L132-147): the recipe must match the stored item and
 * the tool together. The converter leaves out recipes that overlap, so at
 * most one matches and Java's recipe-manager order never matters.
 */
export function findRecipe(recipes, storedId, toolId, hasTag) {
  return recipes.find((r) => r.ingredient.includes(storedId) && toolMatches(r.tool, toolId, hasTag));
}

/**
 * The stacks one cut yields. ChanceResult#rollOutput (L22-33): each of a
 * result's `count` items survives a roll unless random > chance + fortune
 * bonus, the bonus being cuttingBoardFortuneBonus (default 0.1) per Fortune
 * level on the tool (BE L100).
 */
export function rollResults(recipe, fortuneLevel, fortuneBonus, random) {
  const out = [];
  const bonus = fortuneBonus * fortuneLevel;
  for (const result of recipe.results) {
    let amount = result.count;
    for (let roll = 0; roll < result.count; roll++) {
      if (random() > result.chance + bonus) amount--;
    }
    if (amount > 0) out.push({ item: result.item, count: amount });
  }
  return out;
}

const COUNTER_CLOCKWISE = { north: "west", west: "south", south: "east", east: "north" };
const STEP = { north: [0, -1], south: [0, 1], west: [-1, 0], east: [1, 0] };

/**
 * Where results appear and how they move. BE L101-105: from the block's centre,
 * 0.2 blocks toward the board's facing turned counter-clockwise, 0.2 up, moving
 * 0.2 per tick that way. `facing` is Java's facing (the block's
 * minecraft:cardinal_direction; the converter offsets the placement trait so
 * the two agree).
 */
export function spawnOffset(facing) {
  const [x, z] = STEP[COUNTER_CLOCKWISE[facing] ?? "west"];
  return { dx: x * 0.2, dy: 0.2, dz: z * 0.2, vx: x * 0.2, vy: 0, vz: z * 0.2 };
}

/**
 * The sound a cut plays. BE#playProcessingSound (L153-167): the recipe's own
 * sound, else shears, else a knife, else the stored block's break sound, else
 * wood breaking. The stored block's break sound is the block's SoundType, set
 * in code; Bedrock exposes no equivalent to scripts, so that case is silent.
 * A recipe whose Java sound has no Bedrock counterpart has `sound: null`
 * (silent rather than the wrong sound).
 */
export function processingSound(table, recipe, toolId, storedIsBlock) {
  const sounds = table.sounds;
  if (recipe.sound !== undefined) {
    return recipe.sound === null ? null : { ...sounds.recipe, id: recipe.sound };
  }
  if (table.sound_tools.shears.includes(toolId)) return sounds.shears;
  if (table.sound_tools.knife.includes(toolId)) return sounds.knife ?? null;
  if (storedIsBlock) return null;
  return sounds.other;
}

/**
 * How many of `held` go onto the board. BE#canAddItem/addItem (L174-186): the
 * board is one slot holding up to a full stack of one item (the slot limit is
 * the item's max stack size on both loaders), so an empty board takes the
 * whole held stack and a board holding the same item takes what fits.
 * `sameItem` is whether held and stored stack together.
 */
export function amountToAdd(stored, heldAmount, maxAmount, sameItem) {
  if (heldAmount <= 0) return 0;
  if (!stored) return Math.min(heldAmount, maxAmount);
  if (!sameItem) return 0;
  return Math.max(0, Math.min(heldAmount, maxAmount - stored.amount));
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

/** The dynamic-property key holding the board at this position. */
export function storageKey(component, dimensionId, location) {
  return `${component}|${dimensionId}|${location.x},${location.y},${location.z}`;
}
