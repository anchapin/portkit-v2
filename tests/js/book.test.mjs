// The fixed guide book viewer (src/portkit/runtime/book*.js), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/book.test.mjs
// (tests/adapters/citadel/test_books.py runs it with PORTKIT_BOOK_TABLE set to a data table the
// converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import * as core from "../../src/portkit/runtime/book_core.js";
import { registerBooks } from "../../src/portkit/runtime/book.js";
import { _fire, _flush } from "@minecraft/server";
import { FormCancelationReason, _reset, _respond, _shown } from "@minecraft/server-ui";

const FALLBACK = {
  back: "gui.back",
  books: {
    "examplemod:guide": {
      root: "root",
      pages: {
        root: { title: "item.examplemod:field_guide.name", body: "portkit.book.examplemod.guide.root", parent: null,
          links: [["about", "examplemod.book.about"], ["owl", "entity.examplemod:owl.name"]] },
        owl: { title: "entity.examplemod:owl.name", body: "portkit.book.examplemod.guide.owl", parent: "root", links: [] },
        about: { title: null, body: "portkit.book.examplemod.guide.about", parent: "root", links: [] },
      },
    },
  },
  items: { "examplemod:field_guide": "examplemod:guide" },
};

const table = process.env.PORTKIT_BOOK_TABLE
  ? (await import(pathToFileURL(process.env.PORTKIT_BOOK_TABLE).href)).default
  : FALLBACK;

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test("a page view: title, body, links in order, back to the parent", () => {
  const root = core.pageView(table, "examplemod:guide", "root");
  assert.deepEqual(root.title, { translate: "item.examplemod:field_guide.name" });
  assert.deepEqual(root.body, { translate: "portkit.book.examplemod.guide.root" });
  assert.deepEqual(root.buttons.map((b) => b.page), ["about", "owl"]);
  const owl = core.pageView(table, "examplemod:guide", "owl");
  assert.deepEqual(owl.buttons, [{ label: { translate: "gui.back" }, page: "root" }]);
  assert.equal(core.pageView(table, "examplemod:guide", "about").title, "");
  assert.equal(core.pageView(table, "examplemod:guide", "nowhere"), null);
  assert.equal(core.bookFor(table, "examplemod:field_guide"), "examplemod:guide");
  assert.equal(core.bookFor(table, "minecraft:book"), undefined);
});

test("using the item opens the root, a button its page, back returns, closing ends", async () => {
  _reset();
  registerBooks(table);
  const player = { id: "p1" };
  _respond({ canceled: false, selection: 1 }); // root -> owl
  _respond({ canceled: false, selection: 0 }); // owl -> back to root
  _respond({ canceled: true, cancelationReason: FormCancelationReason.UserClosed });
  _fire("after", "itemUse", { source: player, itemStack: { typeId: "examplemod:field_guide" } });
  for (let i = 0; i < 10; i++) await settle();
  assert.equal(_shown.length, 3);
  assert.deepEqual(_shown.map((f) => f.body.translate), [
    "portkit.book.examplemod.guide.root", "portkit.book.examplemod.guide.owl", "portkit.book.examplemod.guide.root"]);
  assert.deepEqual(_shown[1].buttons.map((b) => b.text), [{ translate: "gui.back" }]);
  assert.equal(_shown[0].player, player);
});

test("a busy player gets the form again; another item opens nothing", async () => {
  _reset();
  const player = { id: "p2" };
  _respond({ canceled: true, cancelationReason: FormCancelationReason.UserBusy });
  _respond({ canceled: true, cancelationReason: FormCancelationReason.UserClosed });
  _fire("after", "itemUse", { source: player, itemStack: { typeId: "minecraft:stick" } });
  await settle();
  assert.equal(_shown.length, 0);
  _fire("after", "itemUse", { source: player, itemStack: { typeId: "examplemod:field_guide" } });
  for (let i = 0; i < 5; i++) { await settle(); _flush(); }
  for (let i = 0; i < 5; i++) await settle();
  assert.equal(_shown.length, 2);
});
