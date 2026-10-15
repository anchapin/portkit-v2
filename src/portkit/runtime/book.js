// portkit runtime: a guide book read as forms (#182).
//
// Fixed file, copied verbatim into every pack with a Citadel book
// (portkit/runtime/; see docs/decisions.md, 2026-10-15 guide books). The
// generated entry scripts/portkit/main.js calls registerBooks(table) with
// the mod's data table (book_core.js says what it holds).
//
// Java: the book's item opens Citadel's GuiBasicBook screen at its root page
// when used (the item class's use, read from bytecode by the converter). Here
// using the item opens the root page as an ActionFormData: the page title, its
// text as the body, one button per linked page and a back button to the
// parent; choosing a button opens that page, closing the form closes the book.
// Pictures, the two-page spread and anything else the Java item does on use
// are not carried.
//
// Script API: @minecraft/server 2.0.0 (world.afterEvents.itemUse,
// system.run) and @minecraft/server-ui 2.0.0 (ActionFormData; a form shown
// while the player is busy is cancelled with UserBusy and shown again).

import { system, world } from "@minecraft/server";
import { ActionFormData, FormCancelationReason } from "@minecraft/server-ui";
import { bookFor, pageView } from "./book_core.js";

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

/** Show one page to a player; a chosen button opens its page. */
export function openPage(table, player, bookId, pageId) {
  const view = pageView(table, bookId, pageId);
  if (!view) return Promise.resolve();
  const form = new ActionFormData().title(view.title).body(view.body);
  for (const button of view.buttons) form.button(button.label);
  return show(form, player).then((response) => {
    if (response.canceled || response.selection === undefined) return undefined;
    const chosen = view.buttons[response.selection];
    return chosen ? openPage(table, player, bookId, chosen.page) : undefined;
  });
}

/** Open the book a used item names, at its root page. */
export function used(table, event) {
  const { source: player, itemStack } = event;
  if (!player || !itemStack) return undefined;
  const bookId = bookFor(table, itemStack.typeId);
  if (!bookId) return undefined;
  return openPage(table, player, bookId, table.books[bookId].root);
}

/** Register the book viewer for one mod's data table. */
export function registerBooks(table) {
  world.afterEvents.itemUse.subscribe((event) => {
    // A player who leaves with a form open rejects show(); nothing to do then.
    used(table, event)?.catch(() => undefined);
  });
}
