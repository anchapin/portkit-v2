// portkit station runtime: Waystones waystones, sharestones, portstones, warp plates, warp portals, scrolls and the warp stone, Bedrock binding (#178).
//
// Fixed file, copied verbatim into every pack that ships waystones
// (portkit/runtime/; see docs/decisions.md). The generated entry
// scripts/portkit/main.js calls registerWaystones(table) with the mod's data
// table. Script API: @minecraft/server 2.0.0 (custom components v2:
// beforeOnPlayerPlace, onPlayerInteract, onPlayerBreak, onTick; world, entity
// and item stack dynamic properties; Entity.teleport; Dimension.getEntities;
// system.runInterval; world.afterEvents.playerPlaceBlock) and
// @minecraft/server-ui 2.0.0 (ActionFormData, ModalFormData).
//
// Storage: a waystone is one world dynamic property keyed by its dimension
// and lower-half position (JSON: uid, type, order, dimension, pos, facing,
// name, owner, origin); a player's activated waystones are a player dynamic
// property (JSON list of uids, in activation order). Java keeps the same facts
// in WaystoneManagerImpl and PlayerWaystoneManager's saved data.
//
// Networks: the table maps each block to its Java waystone type and each type
// to a network. A waystone's (not shared) lists the waystones the player
// activated; a sharestone's (shared, one per colour) lists every sharestone of
// its type and has nothing to activate. A portstone (table.portstones) is no
// waystone: it stores nothing, and using it opens the menu of the network it
// targets with no waystone in use, so nothing is left out and no distance is
// checked. A waystone's runes (table.rune_blocks) are a block state the
// runtime turns on when a player activates it.
//
// Warp plates (table.warp_plates) have their own custom component: a plate is
// a record of type warp_plate (never in a menu) holding one shard ({id,
// attunement}); it ticks every tick (minecraft:tick) to attune a dormant
// shard and to warp what stands on it; an attuned shard item carries its
// plate's uid as an item dynamic property. Each entity's warp plate state is
// kept in memory, as Java keeps it unsaved on the entity.
//
// Warp portals (table.warp_portals): a portal scroll held for its use time
// (a script timer: world.afterEvents.itemUse starts it, switching away from
// the scroll or taking damage stops it) opens the menu of the player's
// activated waystones; choosing one opens a two-block portal in front of the
// player, a record of type warp_portal holding its target's uid and its age.
// Its lower half ticks every tick (minecraft:tick): what stands in either
// half is teleported to the target, and the portal closes after its
// lifetime. A player who came through keeps the portal's uid (player dynamic
// property) and sees "Return to Portal" in waystone and sharestone menus
// while it stands.
//
// Scrolls (table.scrolls): the warp, return and bound scrolls use the same
// timer as the portal scroll; then the warp scroll opens the menu of the
// player's activated waystones (and "Return to Portal"), the return scroll
// teleports to the return portal or the nearest activated waystone in the
// player's dimension, and the bound scroll to the waystone whose uid it holds
// as an item dynamic property. A blank scroll used on a waystone or
// sharestone gives a bound scroll bound to it.
//
// Warp stone (table.warp_stones): held for its own use time on the same
// timer, it opens the warp scroll's menu; each teleport from it takes one
// durability from the warp stone in the slot it was used from (not in
// creative), breaking it at its maximum.

import { BlockPermutation, EquipmentSlot, GameMode, ItemStack, system, world } from "@minecraft/server";
import { ActionFormData, FormCancelationReason, ModalFormData } from "@minecraft/server-ui";
import * as core from "./waystone_core.js";
import { centre, describe, loadStored, play, rebuild, saveStored } from "./station_storage.js";

// A form shown while the player is still busy (the use that opened it) is
// cancelled with UserBusy; it is shown again on the next tick, this often.
const BUSY_RETRIES = 20;

function show(form, player, retries = BUSY_RETRIES) {
  return form.show(player).then((response) => {
    if (response.canceled && response.cancelationReason === FormCancelationReason.UserBusy && retries > 0) {
      return new Promise((resolve) => system.run(() => resolve(show(form, player, retries - 1))));
    }
    return response;
  });
}

function free(block) {
  // hasSpaceToTeleport L249-253 asks for blocks that don't suffocate; scripts
  // can't read that, so only air and liquid count as room.
  return !!block && (block.isAir || block.isLiquid);
}

function blockAt(dimension, pos) {
  try {
    return dimension.getBlock(pos);
  } catch {
    return undefined; // an unloaded chunk
  }
}

function typeOf(table, record) {
  return core.recordType(record, table.default_type);
}

function network(table, record) {
  return table.networks[typeOf(table, record)];
}

/** The table's entry for a portstone block, or undefined for a waystone or sharestone. */
function portstoneOf(table, typeId) {
  return (table.portstones || {})[typeId];
}

function lowerPos(table, block, permutation) {
  const half = permutation.getState(table.half_state);
  const { x, y, z } = block.location;
  return half === "upper" ? { x, y: y - 1, z } : { x, y, z };
}

function records(table) {
  const prefix = core.recordPrefix(table.namespace);
  return world.getDynamicPropertyIds()
    .filter((key) => key.startsWith(prefix))
    .map((key) => loadStored(key))
    .filter((record) => record && record.uid);
}

function activated(table, player) {
  const raw = player.getDynamicProperty(core.activatedKey(table.namespace));
  try {
    const list = typeof raw === "string" ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function activate(table, player, uid) {
  const next = core.withActivated(activated(table, player), uid);
  player.setDynamicProperty(core.activatedKey(table.namespace), JSON.stringify(next));
}

/**
 * WaystoneRenderer L33-37: a waystone's runes are drawn once the client's
 * player has activated it. A Bedrock block looks the same to every player,
 * so its runes state (table.rune_state, on both halves) is turned on once
 * any player activates it, and stays on.
 */
function showRunes(table, dimension, pos) {
  if (!table.rune_state) return;
  const lower = blockAt(dimension, pos);
  if (!lower || !(table.rune_blocks || []).includes(lower.typeId)) return;
  const upper = blockAt(dimension, { x: pos.x, y: pos.y + 1, z: pos.z });
  for (const block of [lower, upper]) {
    if (!block || block.typeId !== lower.typeId) continue;
    const permutation = block.permutation;
    if (permutation.getState(table.rune_state) === true) continue;
    block.setPermutation(permutation.withState(table.rune_state, true));
  }
}

/** The next placement number (a world counter), so sharestones list in the order they were placed. */
function nextOrder(table) {
  const key = core.orderKey(table.namespace);
  const raw = world.getDynamicProperty(key);
  const next = (typeof raw === "number" ? raw : 0) + 1;
  world.setDynamicProperty(key, next);
  return next;
}

function newUid() {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 0x7fffffff).toString(36)}`;
}

/**
 * The waystone at a lower-half position, created when there is none (a block
 * not placed by a player: WaystoneBlockEntityBase initializes one with no
 * owner and the state's origin, UNKNOWN by default).
 */
function recordAt(table, dimension, pos, permutation, placer, typeId) {
  const key = core.recordKey(table.namespace, dimension.id, pos);
  const type = table.block_types[typeId] || table.default_type;
  let record = loadStored(key);
  // A record of another type is stale (its block was swapped without a
  // player breaking it); this block is a new waystone, as Java's block
  // entity would be.
  if (!record || typeOf(table, record) !== type) {
    record = {
      uid: newUid(),
      type,
      order: nextOrder(table),
      dimension: dimension.id,
      pos,
      facing: permutation.getState("minecraft:cardinal_direction") || "north",
      name: { text: "" },
      owner: placer ? placer.id : null,
      owner_name: placer ? placer.name : null,
      origin: placer ? "PLAYER" : "UNKNOWN",
    };
    saveStored(key, record);
  }
  return record;
}

function message(table, role, args) {
  const msg = { translate: table.messages[role] };
  if (args) msg.with = { rawtext: args };
  return { rawtext: [msg] };
}

/** WaystoneBlockBase#getStateForPlacement L160-173: a replaceable block above, inside the world. */
function beforePlace(event) {
  const above = event.block.above();
  if (!free(above)) event.cancel = true;
}

/**
 * WaystoneBlockBase#setPlacedBy L286-339: the upper half above with the
 * same facing, a new waystone owned by the placer, activated for them (no
 * message), and the settings screen opened to name it.
 */
function placed(table, event) {
  const { block, player } = event;
  if (table.warp_plates && table.warp_plates.blocks.includes(block.typeId)) {
    platePlaced(table, event);
    return;
  }
  if (!table.blocks.includes(block.typeId)) return;
  const permutation = block.permutation;
  if (permutation.getState(table.half_state) !== "lower") return;
  const above = block.above();
  if (above) above.setPermutation(permutation.withState(table.half_state, "upper"));
  // setPlacedBy L299: a portstone's block entity is no waystone, so placing
  // one makes nothing else (no owner, no name, nothing activated).
  if (portstoneOf(table, block.typeId)) return;
  const pos = { ...block.location };
  // A fresh waystone replaces anything stale stored at this spot.
  saveStored(core.recordKey(table.namespace, block.dimension.id, pos), undefined);
  const record = recordAt(table, block.dimension, pos, permutation, player, block.typeId);
  // activateWaystone L60: only a waystone joins the player's activated list.
  if (!network(table, record).shared) {
    activate(table, player, record.uid);
    showRunes(table, block.dimension, pos);
  }
  system.run(() => rename(table, player, record));
}

/** The settings screen, name only (WaystoneEditScreen; EditWaystoneMessage#handle). */
function rename(table, player, record) {
  const form = new ModalFormData()
    // getSettingsMenuProvider L297: "Edit %s" with the block entity's name
    // (WaystoneBlockEntity / SharestoneBlockEntity#getName).
    .title(message(table, "settings", [{ translate: table.messages[network(table, record).name] }]))
    // Java's name box has no label (WaystoneEditScreen L53, Component.empty()).
    .textField("", "", { defaultValue: record.name && record.name.text ? record.name.text : "" })
    .submitButton({ translate: table.messages.save });
  show(form, player).then((response) => {
    if (response.canceled || !response.formValues) return;
    const key = core.recordKey(table.namespace, record.dimension, record.pos);
    const current = loadStored(key);
    if (!current || current.uid !== record.uid) return;
    if (core.editError(current, player.id, table.restricted_origins)) return;
    if (player.dimension.id !== current.dimension || !core.inRange(player.location, current.pos, table.range_sq)) return;
    current.name = core.legalName(response.formValues[0], table.name_max_length, table.messages.untitled);
    saveStored(key, current);
  });
}

function interact(table, event) {
  const { block, dimension, player } = event;
  if (!player) return;
  const permutation = block.permutation;
  if (permutation.getState(table.half_state) === "upper") {
    const below = block.below();
    if (!below || below.typeId !== block.typeId) return; // a lone upper half is no waystone
  }
  const port = portstoneOf(table, block.typeId);
  // WaystoneBlockBase#useItemOn L257-262: a blank scroll in hand skips the
  // block's own use (sneaking or not: the item's useOn runs either way), and
  // BlankScrollItem#useOn L20-43 binds a scroll to a waystone's or
  // sharestone's waystone; a portstone's block entity holds none, so nothing.
  const held = heldItem(player);
  if (held && table.scrolls && table.scrolls.blank.includes(held.typeId)) {
    if (!port) bind(table, player, recordAt(table, dimension, lowerPos(table, block, permutation), permutation,
      null, block.typeId), held);
    return;
  }
  // PortstoneBlock#useWithoutItem L133-143: the menu of its target network,
  // sneaking or not, with no source waystone.
  if (port) {
    system.run(() => menu(table, player, {
      type: port.target,
      requirements: port.requirements,
      title: { translate: port.title },
      from: null,
    }));
    return;
  }
  const pos = lowerPos(table, block, permutation);
  const record = recordAt(table, dimension, pos, permutation, null, block.typeId);
  // handleEditActions L196-205: sneaking opens the settings.
  if (player.isSneaking) {
    if (core.editError(record, player.id, table.restricted_origins)) {
      player.onScreenDisplay.setActionBar(message(table, "only_owner"));
      return;
    }
    system.run(() => rename(table, player, record));
    return;
  }
  // SharestoneBlock#handleActivation L74-82: the menu, nothing to activate.
  // WaystoneBlock#handleActivation L81-123.
  if (network(table, record).shared || activated(table, player).includes(record.uid)) {
    // Runes missing on a waystone this player has activated (its upper half
    // was replaced, or it predates them) come back on its next use.
    if (!network(table, record).shared) showRunes(table, dimension, pos);
    system.run(() => menu(table, player, {
      type: typeOf(table, record),
      requirements: network(table, record).requirements,
      title: { translate: table.messages.title },
      from: record,
    }));
    return;
  }
  activate(table, player, record.uid);
  showRunes(table, dimension, pos);
  player.sendMessage(message(table, "activated", [core.nameText(record.name)]));
  play(dimension, centre(block), table.sounds.activate);
}

function context(player, target) {
  return {
    is_interdimensional: player.dimension.id !== target.dimension,
    distance: core.distance(player.location, target.pos),
  };
}

/**
 * The selection menu (WaystoneSelectionScreen), then the teleport. `source`
 * is {type, requirements, title, from}: the network listed, the cost rules,
 * the form title, and the waystone in use (null from a portstone: Java's
 * screen then has no "Current Location" header, L333-337).
 */
function menu(table, player, source) {
  const { from } = source;
  const net = table.networks[source.type];
  const list = core.menuTargets(net.shared, activated(table, player), records(table), source.type,
    from ? from.uid : null, table.default_type);
  // getTargetsForWaystone L318: a waystone's or sharestone's menu ends with
  // the portal the player last came through, while it stands.
  // The warp scroll's menu has it too (getTargetsForItem L299-304).
  const back = (from || source.back) && table.warp_portals ? returnPortal(table, player) : undefined;
  if (back) list.push(back);
  const body = [];
  if (from) body.push(message(table, "current_location", [core.nameText(from.name, table.messages.unnamed)]));
  if (list.length === 0) {
    if (body.length) body.push({ text: "\n" });
    body.push(message(table, net.none));
  }
  const form = new ActionFormData().title(source.title).body(body.length ? { rawtext: body } : "");
  for (const target of list) {
    const points = core.cost(requirementsTo(table, source, target), context(player, target));
    const label = [core.nameText(target.name, table.messages.unnamed)];
    if (points > 0) label.push({ text: "\n" }, message(table, "xp_cost", [{ text: String(points) }]));
    form.button({ rawtext: label });
  }
  show(form, player).then((response) => {
    if (response.canceled || response.selection === undefined) return;
    const target = list[response.selection];
    if (!target) return;
    // The portal scroll's menu opens a portal instead (SelectWaystoneMessage L52-58).
    if (source.select) source.select(target);
    else teleport(table, player, source, target);
  });
}

/** The cost rules of a teleport from `source` to `target`: "Return to Portal" has its own per menu type. */
function requirementsTo(table, source, target) {
  if (source.requirementsFor) return source.requirementsFor(target);
  if (table.warp_portals && target.type === table.warp_portals.type) {
    return table.warp_portals.return_requirements[source.type] || [];
  }
  return source.requirements;
}

/** SelectWaystoneMessage -> WaystoneTeleportManager#tryTeleport. */
function teleport(table, player, source, target) {
  const { from } = source;
  const fail = (role) => player.onScreenDisplay.setActionBar(message(table, role));
  // validateTeleportStart L449-452: still near the waystone used; with no
  // waystone in use (a portstone) there is nothing to be near (L523-528).
  if (from && (player.dimension.id !== from.dimension || !core.inRange(player.location, from.pos, table.range_sq))) {
    return fail("out_of_range");
  }
  const key = core.recordKey(table.namespace, target.dimension, target.pos);
  const current = loadStored(key);
  // "Return to Portal" names a warp portal's waystone, not one of the menu's type.
  const toPortal = !!table.warp_portals && target.type === table.warp_portals.type;
  const wanted = toPortal ? table.warp_portals.type : source.type;
  if (!current || current.uid !== target.uid || typeOf(table, current) !== wanted) return fail("missing");
  const dimension = world.getDimension(current.dimension);
  const lower = blockAt(dimension, current.pos);
  if (lower && (toPortal ? !isPortal(table, lower.typeId) : table.block_types[lower.typeId] !== typeOf(table, current))) {
    // The block went without a player breaking it; Java's onRemove drops it.
    saveStored(key, undefined);
    return fail("missing");
  }
  const points = core.cost(requirementsTo(table, source, current), context(player, current));
  const creative = player.getGameMode() === GameMode.Creative;
  if (!core.canAfford(player.getTotalXp(), points, creative)) return fail("not_enough_xp");
  // consumeRequirements L490-494: giveExperiencePoints(-points), creative too.
  if (points > 0) player.addExperience(-points);
  land(table, player, current, lower, dimension);
}

/**
 * WaystoneTeleportManager#resolveDefaultDestination L275-284 and
 * performTeleport L161-162: `entity` lands beside the waystone `current` on
 * its first free side (its own block when its chunk isn't loaded, `lower`
 * undefined), turned to face that side, with the travel sounds.
 */
function land(table, entity, current, lower, dimension) {
  let side = current.facing;
  if (lower) {
    side = core.offsetDirection(current.facing, (direction) => {
      const offset = core.OFFSETS[direction];
      const at = { x: current.pos.x + offset.x, y: current.pos.y, z: current.pos.z + offset.z };
      return free(blockAt(dimension, at)) && free(blockAt(dimension, { ...at, y: at.y + 1 }));
    });
  }
  const destination = core.destination(current.pos, side, current.facing);
  const departure = { ...entity.location };
  const sourceDimension = entity.dimension;
  const rotation = entity.getRotation ? entity.getRotation() : { x: 0, y: 0 };
  entity.teleport(destination.location, {
    dimension,
    rotation: { x: rotation.x, y: destination.yaw },
  });
  play(sourceDimension, departure, table.sounds.depart);
  play(dimension, destination.location, table.sounds.arrive);
}

/**
 * WaystoneBlockBase#playerWillDestroy L96-137 and onRemove L217-237: the
 * other half goes too, and with it the waystone. Only the lower half drops
 * (its loot table); breaking the upper half outside creative destroys the
 * lower one with its drops, as Java drops the lower state's loot.
 */
function broken(table, event) {
  const { block, brokenBlockPermutation: permutation, dimension, player } = event;
  const half = permutation.getState(table.half_state);
  const other = half === "upper" ? block.below() : block.above();
  const pos = half === "upper" ? { ...block.location, y: block.location.y - 1 } : { ...block.location };
  if (other && other.typeId === permutation.type.id && other.permutation.getState(table.half_state) !== half) {
    const creative = player && player.getGameMode() === GameMode.Creative;
    if (half === "upper" && !creative) {
      dimension.runCommand(core.destroyCommand(other.location));
    } else {
      other.setType("minecraft:air");
    }
  }
  // A portstone stores nothing; whatever is stored at its spot is stale.
  saveStored(core.recordKey(table.namespace, dimension.id, pos), undefined);
}

// -- warp plates ---------------------------------------------------------------

// Entity id -> {entity, plate, onPlate, since} (waystone_core.newTracking).
const tracked = new Map();
// Plate record key -> its dormant shard's attunement ticks (Java's
// attunementTicks, unsaved too).
const attuning = new Map();

function plateKey(table, dimensionId, pos) {
  return core.recordKey(table.namespace, dimensionId, pos);
}

function isPlayer(entity) {
  return entity.typeId === "minecraft:player";
}

function creative(entity) {
  return isPlayer(entity) && entity.getGameMode() === GameMode.Creative;
}

function trackingOf(entity) {
  let t = tracked.get(entity.id);
  if (!t) {
    t = { entity, ...core.newTracking() };
    tracked.set(entity.id, t);
  }
  t.entity = entity;
  return t;
}

/**
 * The plate record at a position, made when there is none: a plate placed by
 * a player is owned by them, one placed otherwise has no owner and origin
 * UNKNOWN (WaystoneBlockEntityBase#initializeWaystone); either way it starts
 * with a dormant shard (WarpPlateBlockEntity#initializeWaystone L67-80,
 * initializeInventory L82-84).
 */
function plateRecord(table, dimension, pos, placer) {
  const plates = table.warp_plates;
  const key = plateKey(table, dimension.id, pos);
  let record = loadStored(key);
  if (!record || record.type !== plates.type) {
    record = {
      uid: newUid(),
      type: plates.type,
      order: nextOrder(table),
      dimension: dimension.id,
      pos,
      owner: placer ? placer.id : null,
      owner_name: placer ? placer.name : null,
      origin: placer ? "PLAYER" : "UNKNOWN",
      shard: { id: plates.shards.dormant, attunement: null },
    };
    saveStored(key, record);
  }
  return record;
}

/** setShardItem L333-339: store the shard and show the idle state it gives. */
function setShard(table, block, record, shard) {
  record.shard = shard;
  saveStored(plateKey(table, record.dimension, record.pos), record);
  setStatus(table, block, core.idleStatus(shard, table.warp_plates.shards));
}

function setStatus(table, block, status) {
  const state = table.warp_plates.status_state;
  const permutation = block.permutation;
  if (permutation.getState(state) !== status) block.setPermutation(permutation.withState(state, status));
}

function statusOf(table, block) {
  return block.permutation.getState(table.warp_plates.status_state);
}

/** A held shard as stored: describe() plus its attunement (an item dynamic property). */
function shardOf(table, stack) {
  const raw = stack.getDynamicProperty ? stack.getDynamicProperty(table.warp_plates.attunement_property) : undefined;
  return { ...describe(stack, 1), attunement: typeof raw === "string" ? raw : null };
}

/** A stored shard as an ItemStack; an attunement only fits a non-stackable item. */
function shardStack(table, shard) {
  const stack = rebuild(shard, 1);
  if (shard.attunement && stack.maxAmount === 1) {
    stack.setDynamicProperty(table.warp_plates.attunement_property, shard.attunement);
  }
  return stack;
}

function dropShard(table, dimension, shard, at) {
  dimension.spawnItem(shardStack(table, shard), at);
}

/** Every warp plate record with `uid`, or undefined (WaystoneProxy by uid). */
function plateByUid(table, uid) {
  if (!uid) return undefined;
  return records(table).find((r) => r.uid === uid && r.type === table.warp_plates.type);
}

/**
 * The plate a shard warps to: {uid, record}. uid null: no attunement (Java's
 * "no target"); record undefined: its plate is gone ("invalid target"). A
 * record whose loaded block is no plate any more is forgotten (Java's
 * onRemove drops it).
 */
function warpTarget(table, record) {
  const uid = core.targetUid(record.shard, table.warp_plates.shards, record.uid);
  let target = plateByUid(table, uid);
  if (target) {
    const block = blockAt(world.getDimension(target.dimension), target.pos);
    if (block && !table.warp_plates.blocks.includes(block.typeId)) {
      saveStored(plateKey(table, target.dimension, target.pos), undefined);
      target = undefined;
    }
  }
  return { uid, record: target };
}

function plateCost(table, entity, target) {
  return core.cost(table.warp_plates.requirements, context(entity, target));
}

function plateMessage(table, role) {
  return { rawtext: [{ text: table.warp_plates.error_style }, { translate: table.messages[role] }] };
}

function entitiesOn(dimension, pos) {
  let found = [];
  try {
    found = dimension.getEntities({ location: pos, volume: { x: 1, y: 1, z: 1 } });
  } catch {
    return [];
  }
  return found.filter((e) => (e.isValid === undefined || e.isValid) && core.inBlock(e.location, pos));
}

function riding(entity) {
  return !!entity.getComponent("minecraft:riding");
}

function denied(table, entity) {
  return table.warp_plates.deny.includes(entity.typeId);
}

/** WarpPlateBlock#setPlacedBy (WaystoneBlockBase L286-339): a new plate owned by the placer. */
function platePlaced(table, event) {
  const { block, player } = event;
  const pos = { ...block.location };
  const key = plateKey(table, block.dimension.id, pos);
  saveStored(key, undefined);
  attuning.delete(key);
  const record = plateRecord(table, block.dimension, pos, player);
  setStatus(table, block, core.idleStatus(record.shard, table.warp_plates.shards));
}

/**
 * WarpPlateBlock#useItemOn L163-176 and useWithoutItem L178-201. A player
 * sneaking with anything in either hand never uses a block (vanilla
 * ServerPlayerGameMode#useItemOn); a warp shard in the main hand goes in when
 * the plate holds none (creative keeps the item); sneaking with empty hands
 * pops the shard out. The settings screen Java opens otherwise is not
 * carried.
 */
function plateInteract(table, event) {
  const { block, dimension, player } = event;
  if (!player) return;
  const plates = table.warp_plates;
  const equippable = player.getComponent("minecraft:equippable");
  const main = equippable ? equippable.getEquipment(EquipmentSlot.Mainhand) : undefined;
  const off = equippable ? equippable.getEquipment(EquipmentSlot.Offhand) : undefined;
  if (player.isSneaking && (main || off)) return;
  const pos = { ...block.location };
  const record = plateRecord(table, dimension, pos, null);
  if (main && plates.shards.accepted.includes(main.typeId)) {
    if (record.shard) return;
    const shard = shardOf(table, main);
    if (!creative(player)) {
      if (main.amount > 1) {
        main.amount -= 1;
        equippable.setEquipment(EquipmentSlot.Mainhand, main);
      } else {
        equippable.setEquipment(EquipmentSlot.Mainhand, undefined);
      }
    }
    setShard(table, block, record, shard);
    return;
  }
  if (player.isSneaking && record.shard) {
    dropShard(table, dimension, record.shard, centre(block));
    setShard(table, block, record, null);
  }
}

/**
 * Breaking a plate (WaystoneBlockBase#playerWillDestroy L128-133, onRemove
 * L217-237): outside creative its shard drops; the plate is forgotten.
 */
function plateBroken(table, event) {
  const { block, dimension, player } = event;
  const pos = { ...block.location };
  const key = plateKey(table, dimension.id, pos);
  const record = loadStored(key);
  if (record && record.type === table.warp_plates.type && record.shard && !(player && creative(player))) {
    dropShard(table, dimension, record.shard, centre(block));
  }
  saveStored(key, undefined);
  attuning.delete(key);
}

/** WarpPlateBlockEntity#onEntityCollision L115-142 (WarpPlateBlock#entityInside L108-113). */
function collide(table, block, record, entity, key) {
  const plates = table.warp_plates;
  if (riding(entity) || denied(table, entity)) return;
  const t = trackingOf(entity);
  if (core.onCooldown(t, key)) return;
  if (statusOf(table, block) !== "idle" || !core.hasPotentialTarget(record.shard, plates.shards)) return;
  core.startTracking(t, key);
  const target = warpTarget(table, record);
  const affords = !target.record || !isPlayer(entity) || creative(entity)
    || core.canAfford(entity.getTotalXp(), plateCost(table, entity, target.record), false);
  setStatus(table, block, target.record && affords ? "warping" : "warping_invalid");
}

/**
 * teleportToTarget L265-282 -> WaystoneTeleportManager#tryTeleportAsync:
 * a player who can't pay is told so (not in creative); the target must still
 * be there; the player pays (consumeRequirements); the entity lands on the
 * target plate's centre, turned north (a plate has no facing:
 * resolveDefaultDestination L275-284, no side offset for a warp plate
 * L245-247), marked for the cooldown there (performTeleport L155-158); a
 * single-use shard is used up (not by a creative player).
 */
function warp(table, block, record, entity, target) {
  const plates = table.warp_plates;
  const player = isPlayer(entity);
  const points = plateCost(table, entity, target);
  if (player && !core.canAfford(entity.getTotalXp(), points, creative(entity))) {
    entity.onScreenDisplay.setActionBar(plateMessage(table, "not_enough_xp"));
    return;
  }
  const dimension = world.getDimension(target.dimension);
  if (player && points > 0) entity.addExperience(-points);
  const destination = core.destination(target.pos, null, "north");
  const departure = { ...entity.location };
  const sourceDimension = entity.dimension;
  const rotation = entity.getRotation ? entity.getRotation() : { x: 0, y: 0 };
  entity.teleport(destination.location, { dimension, rotation: { x: rotation.x, y: destination.yaw } });
  core.markCooldown(trackingOf(entity), plateKey(table, target.dimension, target.pos), plates.cooldown);
  play(sourceDimension, departure, table.sounds.depart);
  play(dimension, destination.location, table.sounds.arrive);
  if (record.shard && plates.shards.single_use.includes(record.shard.id) && !creative(entity)) {
    // ItemStack#shrink on the slot's stack (no setShardItem, so no new state).
    record.shard = null;
    saveStored(plateKey(table, record.dimension, record.pos), record);
  }
}

/** WarpPlateBlockEntity#serverTick L169-234, after the collisions of this tick. */
function plateTick(table, event) {
  const plates = table.warp_plates;
  const { block, dimension } = event;
  if (!plates.blocks.includes(block.typeId)) return;
  const pos = { ...block.location };
  const key = plateKey(table, dimension.id, pos);
  const record = plateRecord(table, dimension, pos, null);
  const on = entitiesOn(dimension, pos);
  for (const entity of on) collide(table, block, record, entity, key);

  const step = core.attune(record.shard, attuning.get(key) ?? 0, plates.shards, record.uid, plates.attunement_ticks);
  attuning.set(key, step.ticks);
  if (step.changed) {
    if (step.eject) {
      dropShard(table, dimension, record.shard, centre(block));
      play(dimension, centre(block), table.sounds.eject);
    }
    setShard(table, block, record, step.shard);
  }

  const status = statusOf(table, block);
  if (status !== "warping" && status !== "warping_invalid") return;
  if (on.length === 0) {
    setStatus(table, block, core.idleStatus(record.shard, plates.shards));
    return;
  }
  if (!core.hasPotentialTarget(record.shard, plates.shards)) return;
  let active = false;
  for (const entity of on) {
    const t = trackingOf(entity);
    if (riding(entity) || denied(table, entity)) {
      core.resetOnPlate(t, key);
      continue;
    }
    if (core.onCooldown(t, key)) continue;
    active = true;
    core.startTracking(t, key);
    if (t.onPlate > plates.use_time) {
      const target = warpTarget(table, record);
      if (target.record) warp(table, block, record, entity, target.record);
      if (isPlayer(entity)) {
        if (!target.uid) entity.onScreenDisplay.setActionBar(plateMessage(table, "no_target"));
        else if (!target.record) entity.onScreenDisplay.setActionBar(plateMessage(table, "invalid_target"));
      }
      core.resetOnPlate(t, key);
    } else {
      t.onPlate += 1;
    }
  }
  if (!active) setStatus(table, block, core.idleStatus(record.shard, plates.shards));
}

/** WarpPlateBlockEntity#tickEntityWarpPlateState L385-405 for every tracked entity, each tick. */
function entityTicks(table) {
  const plates = table.warp_plates;
  for (const [id, t] of tracked) {
    const entity = t.entity;
    if (!entity || (entity.isValid !== undefined && !entity.isValid)) {
      tracked.delete(id);
      continue;
    }
    let onItsPlate = false;
    if (t.plate) {
      const record = loadStored(t.plate);
      onItsPlate = !!record && record.dimension === entity.dimension.id && core.inBlock(entity.location, record.pos);
    }
    core.entityTick(t, onItsPlate, plates.cooldown);
    if (core.idleTracking(t, onItsPlate)) tracked.delete(id);
  }
}

// -- warp portals ----------------------------------------------------------------

// Portal record key -> its age in ticks (WarpPortalBlockEntity's Age); written
// to the record every AGE_SAVE ticks, so a reload loses at most that many.
const portalAges = new Map();
const AGE_SAVE = 20;
// Entity id -> the portal clock tick it last used a portal
// (WarpPortalManager.portalCooldowns, unsaved, keyed by tickCount).
const portalUses = new Map();
// Player id -> {player, slot, typeId, ticks, useTime}: a scroll in use.
const charging = new Map();
// Ticks counted by the portal interval (Java counts each entity's tickCount).
let portalClock = 0;

function isPortal(table, typeId) {
  return !!table.warp_portals && table.warp_portals.blocks.includes(typeId);
}

/** A DARK_RED text (PortalScrollItem L36, WarpPortalManager L116-124). */
function portalError(table, role) {
  return { rawtext: [{ text: table.warp_portals.error_style }, { translate: table.messages[role] }] };
}

/**
 * ScrollItemBase#use L37-49: a use that is not already going on plays
 * PORTAL_TRIGGER at the player and starts using the scroll for its use time
 * (getUseDuration: general.scrollUseTime); no use time finishes at once.
 */
function scrollUsed(table, event) {
  const { source: player, itemStack } = event;
  if (!player || !itemStack) return;
  const useTime = scrollUseTime(table, itemStack.typeId);
  if (useTime === undefined) return;
  if (charging.has(player.id)) return;
  play(player.dimension, player.location, table.sounds.scroll_start);
  if (useTime <= 0) {
    scrollDone(table, player, itemStack.typeId);
    return;
  }
  charging.set(player.id, { player, slot: player.selectedSlotIndex, typeId: itemStack.typeId, ticks: 0, useTime });
}

/**
 * A held item's use time (getUseDuration: general.scrollUseTime for a
 * scroll, general.warpStoneUseTime for the warp stone), or undefined for any
 * other item.
 */
function scrollUseTime(table, typeId) {
  if (table.warp_portals && table.warp_portals.scroll.items.includes(typeId)) return table.warp_portals.scroll.use_time;
  if (table.scrolls && table.scrolls.items[typeId]) return table.scrolls.use_time;
  if (table.warp_stones && table.warp_stones.items[typeId]) return table.warp_stones.use_time;
  return undefined;
}

/** finishUsingItem of the item used: the portal scroll's, a warp, return or bound scroll's, or the warp stone's. */
function scrollDone(table, player, typeId) {
  if (table.warp_portals && table.warp_portals.scroll.items.includes(typeId)) scrollFinished(table, player);
  else if (table.warp_stones && table.warp_stones.items[typeId]) warpStoneFinished(table, player, typeId);
  else scrollItemFinished(table, player, typeId);
}

function heldAt(player, slot) {
  const inventory = player.getComponent("minecraft:inventory");
  try {
    return inventory && inventory.container ? inventory.container.getItem(slot) : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Each tick of a scroll in use: Java stops using an item the player no
 * longer holds in that hand (LivingEntity#updatingUsingItem); after the use
 * time the use finishes (finishUsingItem). A script can't see the use button
 * released, so letting go does not stop it here.
 */
function scrollTicks(table) {
  for (const [id, c] of charging) {
    const player = c.player;
    if (!player || (player.isValid !== undefined && !player.isValid)) {
      charging.delete(id);
      continue;
    }
    const held = heldAt(player, c.slot);
    if (player.selectedSlotIndex !== c.slot || !held || held.typeId !== c.typeId) {
      charging.delete(id);
      continue;
    }
    c.ticks += 1;
    if (c.ticks >= c.useTime) {
      charging.delete(id);
      scrollDone(table, player, c.typeId);
    }
  }
}

/** findPortalPos L72-92 against this world: solid below, air or liquid for the rest. */
function portalPos(player) {
  const dimension = player.dimension;
  return core.portalPos(player.location, player.getViewDirection(), (pos) => {
    // canPlacePortalAt L94-99 asks for a solid block below and replaceable
    // ones in the portal's two blocks and the one above; scripts can read
    // neither, so anything but air or liquid counts as solid and only air or
    // liquid as replaceable.
    const below = blockAt(dimension, { x: pos.x, y: pos.y - 1, z: pos.z });
    if (!below || below.isAir || below.isLiquid) return false;
    for (let dy = 0; dy <= 2; dy++) {
      if (!free(blockAt(dimension, { x: pos.x, y: pos.y + dy, z: pos.z }))) return false;
    }
    return true;
  });
}

/**
 * PortalScrollItem#finishUsingItem L33-53: no room for a portal says so
 * (chat, DARK_RED); otherwise the menu of the player's activated waystones
 * (withTargetsForPlayer), whose choice opens a portal to it.
 */
function scrollFinished(table, player) {
  const scroll = table.warp_portals.scroll;
  if (!portalPos(player)) {
    player.sendMessage(portalError(table, "no_space"));
    return;
  }
  system.run(() => menu(table, player, {
    type: scroll.network,
    requirements: scroll.requirements,
    title: { translate: scroll.title },
    from: null,
    select: (target) => openPortal(table, player, target),
  }));
}

/**
 * The scroll menu's choice (SelectWaystoneMessage L52-58, the post-teleport
 * handler PortalScrollItem L43-49): WarpPortalManager#spawnPortal L39-62
 * finds the place again, sets both halves facing the player, makes the
 * portal's waystone (WarpPortalBlockEntity#initialize L72-89: a new uid, the
 * target, "Return to Portal"), plays PORTAL_TRAVEL there and uses up one
 * scroll (ItemStack#consume: not in creative); no place says so instead.
 */
function openPortal(table, player, target) {
  const portals = table.warp_portals;
  const pos = portalPos(player);
  if (!pos) {
    player.sendMessage(portalError(table, "no_space"));
    return;
  }
  const dimension = player.dimension;
  const facing = core.portalFacing(player.getRotation().y);
  const typeId = portals.blocks[0];
  for (const [dy, half] of [[0, "lower"], [1, "upper"]]) {
    const block = blockAt(dimension, { x: pos.x, y: pos.y + dy, z: pos.z });
    if (block) {
      block.setPermutation(BlockPermutation.resolve(typeId, {
        "minecraft:cardinal_direction": facing,
        [table.half_state]: half,
      }));
    }
  }
  const key = core.recordKey(table.namespace, dimension.id, pos);
  saveStored(key, {
    uid: newUid(),
    type: portals.type,
    dimension: dimension.id,
    pos,
    facing,
    target: target.uid,
    age: 0,
    name: { translate: table.messages.return_to_portal },
  });
  portalAges.set(key, 0);
  play(dimension, { x: pos.x + 0.5, y: pos.y + 0.5, z: pos.z + 0.5 }, table.sounds.portal_open);
  if (creative(player)) return;
  const inventory = player.getComponent("minecraft:inventory");
  const container = inventory && inventory.container;
  const slot = player.selectedSlotIndex;
  const held = container ? container.getItem(slot) : undefined;
  if (!held || !portals.scroll.items.includes(held.typeId)) return;
  if (held.amount > 1) {
    held.amount -= 1;
    container.setItem(slot, held);
  } else {
    container.setItem(slot, undefined);
  }
}

/**
 * WarpPortalBlockEntity#removePortal L127-137: the portal's waystone goes,
 * FIRE_EXTINGUISH plays, both halves become air.
 */
function closePortal(table, dimension, pos) {
  const key = core.recordKey(table.namespace, dimension.id, pos);
  saveStored(key, undefined);
  portalAges.delete(key);
  play(dimension, { x: pos.x + 0.5, y: pos.y + 0.5, z: pos.z + 0.5 }, table.sounds.portal_close);
  const lower = blockAt(dimension, pos);
  if (lower && isPortal(table, lower.typeId)) lower.setType("minecraft:air");
  const upper = blockAt(dimension, { x: pos.x, y: pos.y + 1, z: pos.z });
  if (upper && isPortal(table, upper.typeId)) upper.setType("minecraft:air");
}

/** The waystone a portal opens to (WaystoneProxy by uid), or undefined when it is gone. */
function portalTarget(table, record) {
  if (!record.target) return undefined;
  const type = table.warp_portals.scroll.network;
  return records(table).find((r) => r.uid === record.target && typeOf(table, r) === type);
}

/**
 * WarpPortalBlockEntity#onEntityInside L107-119 and
 * WarpPortalManager#canUsePortal L101-109, teleportFromPortal L111-126: at
 * most one use per entity per cooldown, none for the deny list; a portal
 * whose target is gone tells a player so (chat) and closes; otherwise the
 * teleport, which a player pays for (and is told on the action bar, DARK_RED,
 * when they can't); a player who goes through keeps the portal as their
 * return portal (setReturnPortal L128-135). Returns true when the portal closed.
 */
function enterPortal(table, dimension, record, entity) {
  const portals = table.warp_portals;
  // Java takes an entity's controlled mount along (EntityTeleportBatch);
  // here riders don't use portals.
  if (riding(entity)) return false;
  if (!core.mayUsePortal(portalUses, entity.id, portalClock, portals.cooldown)) return false;
  if (portals.deny.includes(entity.typeId)) return false;
  const target = portalTarget(table, record);
  if (!target) {
    if (isPlayer(entity)) entity.sendMessage(message(table, "attunement_lost"));
    closePortal(table, dimension, record.pos);
    return true;
  }
  const player = isPlayer(entity);
  const targetDimension = world.getDimension(target.dimension);
  const lower = blockAt(targetDimension, target.pos);
  if (lower && table.block_types[lower.typeId] !== typeOf(table, target)) {
    // isValidInLevel fails (WaystoneImpl L145-148): the waystone is missing.
    saveStored(core.recordKey(table.namespace, target.dimension, target.pos), undefined);
    if (player) entity.onScreenDisplay.setActionBar(portalError(table, "missing"));
    return false;
  }
  const points = core.cost(portals.requirements, context(entity, target));
  if (player && !core.canAfford(entity.getTotalXp(), points, creative(entity))) {
    entity.onScreenDisplay.setActionBar(portalError(table, "not_enough_xp"));
    return false;
  }
  if (player && points > 0) entity.addExperience(-points);
  land(table, entity, target, lower, targetDimension);
  if (player && record.uid) entity.setDynamicProperty(portals.return_property, record.uid);
  return false;
}

/**
 * WarpPortalBlockEntity#serverTick L121-125 (the lower half's ticker) and
 * WarpPortalBlock#entityInside L66-74 (either half, acting for the lower):
 * what stands in the portal goes through it, and after its lifetime the
 * portal closes. A portal no scroll opened (placed by command) has no target
 * (Java's block entity defaults), so the first entity in it closes it.
 */
function portalTick(table, event) {
  const portals = table.warp_portals;
  const { block, dimension } = event;
  if (!isPortal(table, block.typeId)) return;
  const permutation = block.permutation;
  if (permutation.getState(table.half_state) === "upper") return;
  const pos = { ...block.location };
  const key = core.recordKey(table.namespace, dimension.id, pos);
  let record = loadStored(key);
  if (!record || record.type !== portals.type) {
    record = {
      uid: null,
      type: portals.type,
      dimension: dimension.id,
      pos,
      facing: permutation.getState("minecraft:cardinal_direction") || "north",
      target: null,
      age: 0,
    };
    saveStored(key, record);
  }
  const seen = new Set();
  for (const at of [pos, { x: pos.x, y: pos.y + 1, z: pos.z }]) {
    for (const entity of entitiesOn(dimension, at)) {
      if (seen.has(entity.id)) continue;
      seen.add(entity.id);
      if (enterPortal(table, dimension, record, entity)) return;
    }
  }
  const age = (portalAges.get(key) ?? record.age ?? 0) + 1;
  if (age >= portals.lifetime) {
    closePortal(table, dimension, pos);
    return;
  }
  portalAges.set(key, age);
  if (age % AGE_SAVE === 0) {
    record.age = age;
    saveStored(key, record);
  }
}

/**
 * WarpPortalManager#getReturnPortal L137-159: the portal the player last came
 * through while it stands (its record, and its block when loaded); a record
 * whose loaded block is no portal any more is forgotten.
 */
function returnPortal(table, player) {
  const portals = table.warp_portals;
  const uid = player.getDynamicProperty ? player.getDynamicProperty(portals.return_property) : undefined;
  if (typeof uid !== "string") return undefined;
  const record = records(table).find((r) => r.uid === uid && r.type === portals.type);
  if (!record) return undefined;
  const dimension = world.getDimension(record.dimension);
  const lower = dimension ? blockAt(dimension, record.pos) : undefined;
  if (lower && !isPortal(table, lower.typeId)) {
    saveStored(core.recordKey(table.namespace, record.dimension, record.pos), undefined);
    return undefined;
  }
  return record;
}

/** Every tick: the portal clock, scrolls in use, and forgetting uses past their cooldown. */
function portalInterval(table) {
  portalClock += 1;
  scrollTicks(table);
  for (const [id, tick] of portalUses) {
    if (portalClock - tick >= table.warp_portals.cooldown) portalUses.delete(id);
  }
}

// -- warp, return and bound scrolls ----------------------------------------------

/** The item in the player's selected slot (Java's used hand here: the main hand). */
function heldItem(player) {
  return typeof player.selectedSlotIndex === "number" ? heldAt(player, player.selectedSlotIndex) : undefined;
}

/** A DARK_RED action-bar text (BoundScrollItem L49-50, SelectWaystoneMessage L64, L86-89). */
function scrollError(table, role) {
  return { rawtext: [{ text: table.scrolls.error_style }, { translate: table.messages[role] }] };
}

/** ItemStack#consume(1, player): one of the scroll in hand goes, not in creative. */
function useUp(player, typeId) {
  if (creative(player)) return;
  const inventory = player.getComponent("minecraft:inventory");
  const container = inventory && inventory.container;
  const slot = player.selectedSlotIndex;
  const held = container ? container.getItem(slot) : undefined;
  if (!held || held.typeId !== typeId) return;
  if (held.amount > 1) {
    held.amount -= 1;
    container.setItem(slot, held);
  } else {
    container.setItem(slot, undefined);
  }
}

/**
 * finishUsingItem of a warp, return or bound scroll: the warp scroll's menu
 * (WarpScrollItem L25-36: getTargetsForItem, the player's activated
 * waystones and the return portal; no source waystone), or a teleport to the
 * bound waystone (BoundScrollItem L37-55) or, for the return scroll, to the
 * return portal or the nearest activated waystone (ReturnScrollItem L19-22).
 * No target does nothing (Optional#ifPresent).
 */
function scrollItemFinished(table, player, typeId) {
  const scrolls = table.scrolls;
  const item = scrolls.items[typeId];
  if (!item) return;
  if (item.kind === "warp") {
    system.run(() => menu(table, player, {
      type: scrolls.network,
      requirementsFor: (target) => scrollRequirements(table, item, target),
      title: { translate: scrolls.title },
      from: null,
      back: true,
      select: (target) => scrollTeleport(table, player, typeId, target, true),
    }));
    return;
  }
  let target;
  if (item.kind === "bound") {
    const held = heldItem(player);
    const uid = held && held.typeId === typeId && held.getDynamicProperty
      ? held.getDynamicProperty(scrolls.binding_property) : undefined;
    // WaystoneProxy by uid: a waystone that no longer exists fails with
    // InvalidWaystone, whose message is empty (WaystoneTeleportError L45-50).
    if (typeof uid === "string") target = records(table).find((r) => r.uid === uid) ?? null;
  } else {
    target = (table.warp_portals ? returnPortal(table, player) : undefined)
      ?? core.nearestWaystone(activated(table, player), records(table), scrolls.network, player.dimension.id,
        player.location, table.default_type);
  }
  if (target) scrollTeleport(table, player, typeId, target, false);
}

/** The cost rules of a teleport with a scroll to `target`, by the target's type (a return portal its own). */
function scrollRequirements(table, item, target) {
  const type = table.warp_portals && target.type === table.warp_portals.type
    ? table.warp_portals.type : typeOf(table, target);
  return item.requirements[type] || [];
}

/**
 * A scroll's teleport (WaystonesAPI#createUncheckedDefaultTeleportContext with
 * the scroll as the warp item, then tryTeleportAsync): from the warp scroll's
 * menu the scroll must still be in hand (isSameItemSameComponents; else
 * SourceItemMissing, SelectWaystoneMessage L60-66); the target must still
 * exist (else nothing: an empty message) with its block (else "missing"); a
 * player who can't pay is told (validateRequirements); then the cost is taken,
 * the player lands beside it and one scroll is used up (the post-teleport
 * handler / ifLeft: consume). Errors go to the action bar in DARK_RED.
 */
function scrollTeleport(table, player, typeId, target, fromMenu) {
  const fail = (role) => player.onScreenDisplay.setActionBar(scrollError(table, role));
  if (fromMenu) {
    const held = heldItem(player);
    if (!held || held.typeId !== typeId) return fail("source_item_missing");
  }
  if (itemTeleport(table, player, table.scrolls.items[typeId], target, table.scrolls.error_style)) {
    useUp(player, typeId);
  }
}

/**
 * The teleport with a warp item (a scroll or the warp stone) to `target`:
 * the target must still exist (else nothing: InvalidWaystone's empty
 * message) with its block (else "missing"); a player who can't pay is told
 * (validateRequirements); then the cost is taken and the player lands beside
 * it. Errors go to the action bar in `style`. True when the player went.
 */
function itemTeleport(table, player, item, target, style) {
  const fail = (role) => {
    player.onScreenDisplay.setActionBar({ rawtext: [{ text: style }, { translate: table.messages[role] }] });
    return false;
  };
  const key = core.recordKey(table.namespace, target.dimension, target.pos);
  const current = loadStored(key);
  if (!current || current.uid !== target.uid) return false;
  const toPortal = !!table.warp_portals && current.type === table.warp_portals.type;
  if (!toPortal && !table.networks[typeOf(table, current)]) return false;
  const dimension = world.getDimension(current.dimension);
  const lower = blockAt(dimension, current.pos);
  if (lower && (toPortal ? !isPortal(table, lower.typeId) : table.block_types[lower.typeId] !== typeOf(table, current))) {
    // The block went without a player breaking it (isValidInLevel fails).
    saveStored(key, undefined);
    return fail("missing");
  }
  const points = core.cost(scrollRequirements(table, item, current), context(player, current));
  if (!core.canAfford(player.getTotalXp(), points, creative(player))) return fail("not_enough_xp");
  if (points > 0) player.addExperience(-points);
  land(table, player, current, lower, dimension);
  return true;
}

// -- the warp stone ----------------------------------------------------------------

/**
 * WarpStoneItem#finishUsingItem L120-135: the menu of getTargetsForItem (the
 * player's activated waystones and the return portal; no source waystone)
 * titled container.waystones.waystone_selection. The menu has no warp hand
 * (no withHand), so SelectWaystoneMessage L60-67 never checks that the stone
 * is still held; the post-teleport handler wears down the stone used.
 */
function warpStoneFinished(table, player, typeId) {
  const stones = table.warp_stones;
  const item = stones.items[typeId];
  const slot = player.selectedSlotIndex;
  system.run(() => menu(table, player, {
    type: stones.network,
    requirementsFor: (target) => scrollRequirements(table, item, target),
    title: { translate: stones.title },
    from: null,
    back: true,
    select: (target) => {
      if (itemTeleport(table, player, item, target, stones.error_style)) wearWarpStone(table, player, typeId, slot);
    },
  }));
}

/**
 * The post-teleport handler (WarpStoneItem L126-130): with
 * teleports.enableDurability, ItemStack#hurtAndBreak(1): nothing for a player
 * with infinite materials (creative); one more damage, and a stack whose
 * damage reaches its maximum breaks (ItemStack L442-470) with the item break
 * sound (LivingEntity#breakItem: 0.8, pitch 0.8 + random * 0.4). Java wears
 * the very stack used, wherever it went; here, the warp stone in the slot it
 * was used from, if one is still there.
 */
function wearWarpStone(table, player, typeId, slot) {
  if (!table.warp_stones.durability || creative(player)) return;
  const inventory = player.getComponent("minecraft:inventory");
  const container = inventory && inventory.container;
  const held = container ? container.getItem(slot) : undefined;
  if (!held || held.typeId !== typeId) return;
  const durability = held.getComponent("minecraft:durability");
  if (!durability) return;
  if (core.wearBreaks(durability.damage, durability.maxDurability)) {
    container.setItem(slot, undefined);
    const sound = table.sounds.item_break;
    play(player.dimension, player.location, sound, sound ? sound.pitch + Math.random() * sound.spread : undefined);
    return;
  }
  durability.damage += 1;
  container.setItem(slot, held);
}

/**
 * BlankScrollItem#useOn L20-43: a bound scroll bound to `record`
 * (WaystonesAPI#setBoundWaystone -> BoundScrollItem#setWaystoneAttunedTo
 * L67-76: its uid and its name), when the inventory has a free slot or, outside
 * creative, the blank scroll in hand is the last; one blank scroll is used up
 * (not in creative), and the bound scroll goes into the inventory or, when it
 * doesn't fit, is dropped at the player.
 */
function bind(table, player, record, held) {
  const scrolls = table.scrolls;
  const inventory = player.getComponent("minecraft:inventory");
  const container = inventory && inventory.container;
  if (!container) return;
  const isCreative = creative(player);
  // A bound scroll holds one (it carries script data), so no slot can take it on top.
  if (!core.mayBind(container.emptySlotsCount ?? 0, false, isCreative, held.amount)) return;
  useUp(player, held.typeId);
  const stack = new ItemStack(scrolls.bound, 1);
  stack.setDynamicProperty(scrolls.binding_property, record.uid);
  const name = record.name && typeof record.name.text === "string" ? record.name.text : "";
  if (name) stack.setLore([`${scrolls.name_style}${name}`]);
  const left = container.addItem(stack);
  if (left) player.dimension.spawnItem(left, player.location);
}

/** Register the waystones' custom component for one mod's data table. */
export function registerWaystones(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      beforeOnPlayerPlace: (event) => beforePlace(event),
      onPlayerInteract: (event) => interact(table, event),
      onPlayerBreak: (event) => broken(table, event),
    });
    if (table.warp_plates) {
      init.blockComponentRegistry.registerCustomComponent(table.warp_plates.component, {
        onTick: (event) => plateTick(table, event),
        onPlayerInteract: (event) => plateInteract(table, event),
        onPlayerBreak: (event) => plateBroken(table, event),
      });
    }
    if (table.warp_portals) {
      init.blockComponentRegistry.registerCustomComponent(table.warp_portals.component, {
        onTick: (event) => portalTick(table, event),
      });
    }
  });
  world.afterEvents.playerPlaceBlock.subscribe((event) => placed(table, event));
  if (table.warp_plates) system.runInterval(() => entityTicks(table), 1);
  if (table.warp_portals || table.scrolls || table.warp_stones) {
    world.afterEvents.itemUse.subscribe((event) => scrollUsed(table, event));
    // WarpDamageResetHandler#onDamage L10-15: damage stops a scroll's use
    // (every scroll and the warp stone is an IResetUseOnDamage).
    world.afterEvents.entityHurt.subscribe((event) => {
      if (event.hurtEntity) charging.delete(event.hurtEntity.id);
    });
    if (table.warp_portals) system.runInterval(() => portalInterval(table), 1);
    else system.runInterval(() => scrollTicks(table), 1);
  }
}
