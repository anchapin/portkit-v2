// portkit runtime: what one page of a guide book shows (#182), no imports.
//
// Fixed file, copied verbatim into every pack with a Citadel book
// (portkit/runtime/; see docs/decisions.md, 2026-10-15 guide books). The
// table is the generated scripts/portkit/data/<namespace>_books.js:
//   items: item id -> book id
//   books: book id -> { root, pages: page -> { title, body, parent, links } }
//   back:  the translation key of the back button (vanilla gui.back)
// title, body and each link's label are translation keys; the text itself is
// in the resource pack's texts/*.lang.
//
// Citadel 1.20 @8c09dce GuiBasicBook: a page shows its title
// (writePageText, I18n of the page's "title"), its text, and a button per
// linked page (addLinkButtons: linked_page_buttons, then entity_buttons); the
// previous-page arrow on a page's first sheet opens its "parent"
// (onSwitchPage L262-280) and is hidden on the root page (writePageText).

/** The book a used item opens, or undefined. */
export function bookFor(table, itemId) {
  const id = table.items[itemId];
  return id && table.books[id] ? id : undefined;
}

/**
 * The form for one page: { title, body, buttons: [{ label, page }] }, title,
 * body and labels as rawtext messages; null for a page the book doesn't have.
 */
export function pageView(table, bookId, pageId) {
  const book = table.books[bookId];
  const page = book && book.pages[pageId];
  if (!page) return null;
  const buttons = page.links
    .filter(([target]) => book.pages[target])
    .map(([target, label]) => ({ label: { translate: label }, page: target }));
  if (pageId !== book.root && page.parent && book.pages[page.parent]) {
    buttons.push({ label: { translate: table.back }, page: page.parent });
  }
  return {
    title: page.title ? { translate: page.title } : "",
    body: page.body ? { translate: page.body } : "",
    buttons,
  };
}
