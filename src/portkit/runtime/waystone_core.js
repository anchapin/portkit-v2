// portkit station runtime: Waystones waystone, sharestone, portstone and warp plate logic (#178).
//
// Fixed file, copied verbatim into every pack that ships waystones
// (portkit/runtime/; see docs/decisions.md). No imports, so it runs under
// node (tests/js/waystone.test.mjs, tests/js/warp_plate.test.mjs). The Bedrock binding is waystone.js.
//
// Cited to Waystones v21.1.46 (TwelveIterations/Waystones @9d280c1a,
// common/src/main/java/net/blay09/mods/waystones/); the data table's header
// lists the exact lines.

/**
 * The experience points a teleport costs: the data table's warp requirement
 * modifiers applied in order to 0 (InternalMethodsImpl#resolveRequirements
 * L244-259; RequirementRegistry L122-147). Each modifier applies when every
 * condition in its `when` matches the context ({is_interdimensional, distance}).
 * Java does the arithmetic in float and casts to int (truncation toward 0),
 * which Math.fround and Math.trunc reproduce.
 */
export function cost(requirements, context) {
  let points = 0;
  for (const modifier of requirements) {
    const applies = Object.entries(modifier.when || {}).every(([name, wanted]) => !!context[name] === wanted);
    if (!applies) continue;
    const [a, b] = modifier.args;
    switch (modifier.fn) {
      case "add_xp_cost":
        points = points + a;
        break;
      case "multiply_xp_cost":
        points = Math.trunc(Math.fround(points * Math.fround(a)));
        break;
      case "scaled_add_xp_cost": {
        const value = Math.fround(context[a] ?? 0);
        points = Math.trunc(Math.fround(points + Math.fround(value * Math.fround(b))));
        break;
      }
      case "min_xp_cost":
        points = Math.max(points, a);
        break;
      case "max_xp_cost":
        points = Math.min(points, a);
        break;
      default:
        throw new Error(`unknown warp requirement ${modifier.fn}`);
    }
  }
  return points;
}

/**
 * ExperiencePointsRequirement#canAfford L17-23 (the player's total points
 * against the cost), skipped in creative (WaystoneTeleportManager
 * #validateRequirements L482: !player.getAbilities().instabuild).
 */
export function canAfford(totalXp, points, creative) {
  return creative || points <= 0 || totalXp >= points;
}

/** Distance from a location to a block position's centre (RequirementRegistry L434). */
export function distance(location, pos) {
  const dx = location.x - (pos.x + 0.5);
  const dy = location.y - (pos.y + 0.5);
  const dz = location.z - (pos.z + 0.5);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

/** WaystoneTeleportManager#canInteractWithWaystone L531: distanceToSqr(centre) <= range. */
export function inRange(location, pos, rangeSq) {
  const d = distance(location, pos);
  return d * d <= rangeSq;
}

export const OFFSETS = {
  north: { x: 0, z: -1 },
  south: { x: 0, z: 1 },
  east: { x: 1, z: 0 },
  west: { x: -1, z: 0 },
};

// Direction#toYRot, wrapped to [-180, 180) (Mth.wrapDegrees): south 0,
// west 90, north 180 (-180), east -90. Bedrock's yaw uses the same axes.
const YAW = { south: 0, west: 90, north: -180, east: -90 };

/**
 * WaystoneTeleportManager#findTeleportOffsetDirection L258-273: the facing
 * first, then east, west, south, north; the first side with room (`free`
 * says whether a side's block and the one above it leave room). null when
 * none does.
 */
export function offsetDirection(facing, free) {
  for (const candidate of [facing, "east", "west", "south", "north"]) {
    if (OFFSETS[candidate] && free(candidate)) return candidate;
  }
  return null;
}

/**
 * WaystoneTeleportManager#resolveDefaultDestination L275-284 and
 * teleportEntity L200: the centre of the block beside the waystone on that
 * side (the waystone's own block when no side has room), the player turned
 * to face the side (or the waystone's facing).
 */
export function destination(pos, side, facing) {
  const offset = side ? OFFSETS[side] : { x: 0, z: 0 };
  return {
    location: { x: pos.x + offset.x + 0.5, y: pos.y + 0.5, z: pos.z + offset.z + 0.5 },
    yaw: YAW[side || facing] ?? YAW.north,
  };
}

/**
 * EditWaystoneMessage#makeNameLegal L84-94: a blank name becomes the
 * untitled key; the edit box holds at most `max` characters
 * (WaystoneEditScreen L54). The inventory-button clash rule never applies
 * (the inventoryButton default is "" and a blank name is untitled first).
 */
export function legalName(input, max, untitledKey) {
  const text = String(input ?? "");
  if (text.trim().length === 0) return { translate: untitledKey };
  return { text: text.slice(0, max) };
}

/** A stored name as rawtext; an empty one as `emptyKey` when given (AbstractWaystoneButton L29-32). */
export function nameText(name, emptyKey) {
  if (name && name.translate) return { translate: name.translate };
  const text = (name && name.text) || "";
  if (!text && emptyKey) return { translate: emptyKey };
  return { text };
}

/**
 * WaystonePermissionManager#mayEditWaystone L35-53 at the defaults: with
 * PLAYER restricted, only the owner edits an owned waystone; a waystone
 * whose origin is restricted can't be edited. Returns "only_owner" or null.
 * (Edit-all permission and the global-visibility rule have no counterpart.)
 */
export function editError(record, playerId, restricted) {
  const owned = !!record.owner;
  if (owned && restricted.includes("PLAYER") && record.owner !== playerId) return "only_owner";
  if (record.origin !== "PLAYER" && restricted.includes(record.origin)) return "only_owner";
  return null;
}

/**
 * The menu's entries: the player's activated waystones in activation order
 * (the default MANUAL sort over the sorting index, which appends waystones
 * as they are activated: PersistentPlayerWaystoneData L270-290), those that
 * still exist, without the one in use (Java lists it disabled,
 * WaystoneList L46-48).
 */
export function targets(activated, records, fromUid) {
  const byUid = new Map(records.map((r) => [r.uid, r]));
  const seen = new Set();
  const list = [];
  for (const uid of activated) {
    if (uid === fromUid || seen.has(uid) || !byUid.has(uid)) continue;
    seen.add(uid);
    list.push(byUid.get(uid));
  }
  return list;
}

/** A stored waystone's type; records written before records carried one are `fallback`'s (#198). */
export function recordType(record, fallback) {
  return (record && record.type) || fallback;
}

/**
 * A sharestone's menu entries: every stored waystone of its type
 * (PlayerWaystoneManager#getTargetsForWaystoneType L325-326 lists
 * WaystoneManagerImpl#getWaystonesByType, every dimension), without the one in
 * use, in the order they were placed (`order`, a world counter, then uid). Java's order is
 * its manager's hash order appended to each player's sorting index, which no
 * rule reproduces; placement order is stable for everyone.
 */
export function sharedTargets(records, type, fromUid, fallback) {
  return records
    .filter((r) => r.uid !== fromUid && recordType(r, fallback) === type)
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || (a.uid < b.uid ? -1 : a.uid > b.uid ? 1 : 0));
}

/**
 * A menu's entries for a network of `type` (PlayerWaystoneManager
 * #getTargetsForWaystoneType L323-333): a shared network (a sharestone colour)
 * lists every stored waystone of that type, any other the player's activated
 * waystones of that type; `fromUid` (the waystone in use, null from a
 * portstone, which is no waystone) is left out.
 */
export function menuTargets(shared, activated, records, type, fromUid, fallback) {
  if (shared) return sharedTargets(records, type, fromUid, fallback);
  return targets(activated, records, fromUid).filter((r) => recordType(r, fallback) === type);
}

/** The player's activated list with `uid` added (PlayerWaystoneManager#activateWaystone). */
export function withActivated(activated, uid) {
  return activated.includes(uid) ? activated : [...activated, uid];
}

/** Dynamic property key of the waystone whose lower half is at `pos` in `dimensionId`. */
export function recordKey(namespace, dimensionId, pos) {
  return `${namespace}:portkit_waystone|${dimensionId}|${pos.x},${pos.y},${pos.z}`;
}

export function recordPrefix(namespace) {
  return `${namespace}:portkit_waystone|`;
}

/** World dynamic property counting placements (a record's `order`). */
export function orderKey(namespace) {
  return `${namespace}:portkit_waystone_order`;
}

/** Player dynamic property holding the uids the player activated, in order. */
export function activatedKey(namespace) {
  return `${namespace}:portkit_waystones`;
}

/** `setblock` that removes the block at `location` and drops its loot (Java's destroyBlock with drops). */
export function destroyCommand(location) {
  return `setblock ${location.x} ${location.y} ${location.z} air destroy`;
}

// -- warp plates ---------------------------------------------------------------
// WarpPlateBlockEntity (block/entity/WarpPlateBlockEntity.java). A plate holds
// one shard ({id, attunement}: Java's container slot 0; the modifier slots 1-4
// have no counterpart, so no modifier ever applies).

/**
 * getIdleState L145-157: no shard EMPTY, the locking shard LOCKED, the
 * dormant shard ATTUNING, anything else IDLE. (REDSTONE_DISABLED needs a
 * redstone torch in a modifier slot, which never holds anything here.)
 */
export function idleStatus(shard, shards) {
  if (!shard) return "empty";
  if (shards.locked && shard.id === shards.locked) return "locked";
  if (shard.id === shards.dormant) return "attuning";
  return "idle";
}

/** hasPotentialWarpTarget L105-108: any shard but the locking one. */
export function hasPotentialTarget(shard, shards) {
  return !!shard && !(shards.locked && shard.id === shards.locked);
}

/**
 * getTargetAttunementStack L293-320 with one slot: the waystone the shard is
 * attuned to, unless it is this plate's own (or the item is no warp shard);
 * null for none (Java's EMPTY stack, so getBoundWaystone is empty).
 */
export function targetUid(shard, shards, selfUid) {
  if (!shard || !shards.accepted.includes(shard.id)) return null;
  const uid = shard.attunement;
  return uid && uid !== selfUid ? uid : null;
}

/**
 * attuneShard L345-376, one tick: a dormant shard counts up and at
 * `maxTicks` (getMaxAttunementTicks L377-379) becomes an attuned shard bound
 * to this plate; an attuned shard bound to this plate is popped out
 * (`eject`); anything else resets the count. Returns {shard, ticks, changed, eject}.
 */
export function attune(shard, ticks, shards, selfUid, maxTicks) {
  if (shard && shard.id === shards.dormant) {
    const next = ticks + 1;
    if (next >= maxTicks) return { shard: { id: shards.attuned, attunement: selfUid }, ticks: 0, changed: true, eject: false };
    return { shard, ticks: next, changed: false, eject: false };
  }
  if (shard && shard.id === shards.attuned && shard.attunement === selfUid) {
    return { shard: null, ticks, changed: true, eject: true };
  }
  return { shard, ticks: 0, changed: false, eject: false };
}

/**
 * An entity's warp plate state (Java keeps it on the entity, EntityMixin
 * L17-28, unsaved): the plate it was last tracked on (`plate`, a record key),
 * ticks spent on it (`onPlate`) and the cooldown ticks left (`since`).
 */
export function newTracking() {
  return { plate: null, onPlate: 0, since: 0 };
}

/** isOnWarpPlateCooldown L420-423. */
export function onCooldown(t, plate) {
  return t.plate === plate && t.since > 0;
}

/** startTrackingEntity L407-412. */
export function startTracking(t, plate) {
  if (t.plate !== plate) {
    t.plate = plate;
    t.onPlate = 0;
  }
}

/** resetTicksPassedOnWarpPlate L414-418. */
export function resetOnPlate(t, plate) {
  if (t.plate === plate) t.onPlate = 0;
}

/** markEntityForCooldown L326-331: an entity that arrived on `plate`. */
export function markCooldown(t, plate, cooldown) {
  t.plate = plate;
  t.onPlate = 0;
  t.since = cooldown;
}

/**
 * tickEntityWarpPlateState L385-405, one entity tick: off its plate (or with
 * none) the count resets and the cooldown runs down; on it, a running
 * cooldown starts over.
 */
export function entityTick(t, onItsPlate, cooldown) {
  if (t.plate && onItsPlate) {
    if (t.since > 0) t.since = cooldown;
    return;
  }
  t.onPlate = 0;
  if (t.since > 0) t.since -= 1;
}

/** Whether a tracking entry says nothing a fresh one wouldn't (it can be dropped). */
export function idleTracking(t, onItsPlate) {
  return !onItsPlate && t.onPlate === 0 && t.since <= 0;
}

/** Whether an entity position lies in the block at `pos` (getEntitiesOnTop L159-167: the block's own cube). */
export function inBlock(location, pos) {
  return Math.floor(location.x) === pos.x && Math.floor(location.y) === pos.y && Math.floor(location.z) === pos.z;
}
