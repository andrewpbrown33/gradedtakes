# APP MODE — the pages inside the native app

The Graded Takes iPhone app (`ios/`) shows the very same HTML pages the
browser and the installed web app show, inside a `WKWebView`. The app
draws its own header (title, league switcher, week) and its own tab bar
(Home / Lineup / Board / Ledger / Trade) around that web view. Without
this contract the reader sees two headers and two tab bars — a quarter of
the screen spent on navigation drawn twice.

This is the whole contract. It lives in `engine/ui.py` (`APP_MODE_CSS`,
`shell()`), is asserted by `tests/ui_test.py` [11] and
`tests/prefs_test.py` [1], and reaches every page through `ui.css()` — no
renderer has to know about it.

## The attribute

The native app sets **one attribute on the root element, before first
paint** — it stamps the `<html>` tag of every HTML document it serves
(`ios/GradedTakes/Web/PageSchemeHandler.swift`), so the attribute is there
before the parser reaches the first inline script:

```html
<html data-app="ios">
```

| Name       | Value | Set by                  | Seen by                              |
|------------|-------|-------------------------|--------------------------------------|
| `data-app` | `ios` | the native app, in the served markup | `APP_MODE_CSS` (by value), the shell's scripts (by presence) |

The pages **never** set it themselves: `ui.shell()` emits no `data-app`,
and no renderer does. A page opened in Safari, Chrome, or from the home
screen has no such attribute and looks exactly as it always did. Today the
only value is `ios`; other values are reserved (the CSS would need one more
selector, the scripts already step aside for any `data-app`).

## What hides

Under `html[data-app="ios"]`, and only there:

* **`.wr-nav`** — the sticky header, whole: the gold-diamond wordmark
  (GRADED TAKES), the league switcher that doubles as the page title, the
  nav links, the `WK n` badge, the Light/Dark theme toggle and the
  preferences gear (`engine/prefs.py`'s `<details>` sits inside the header,
  so its sheet goes with it).
* **`.wr-nav-sub`** — the navy subtitle strip that sits directly under the
  bar on the Lineup and Trade Desk pages. It is the bar's second row, so it
  leaves with the bar.
* **`.wr-tabs`** — the five-tab phone bar (`display: flex` under 700px in
  a browser; `display: none` at every width in app mode).

And the space they reserved is released:

* `--wr-nav-h` → `0px` and `html { scroll-padding-top: 0 }`, so an in-page
  `#anchor` jump lands at the very top instead of clearing a bar that is
  no longer there.
* `body { padding-bottom }` — the 60px (+ home indicator) kept for the
  fixed tab bar — becomes `env(safe-area-inset-bottom, 0px)`: the device's
  own bottom inset and nothing more. The native app encloses the web view
  inside the safe area (`contentInsetAdjustmentBehavior = .never`), so this
  resolves to 0 there and content runs to the bottom of the web view.

The exact rules:

```css
html[data-app="ios"] .wr-nav,
html[data-app="ios"] .wr-nav-sub,
html[data-app="ios"] .wr-tabs { display: none; }
html[data-app="ios"] { --wr-nav-h: 0px; scroll-padding-top: 0; }
html[data-app="ios"] body { padding-bottom: env(safe-area-inset-bottom, 0px); }
```

Every selector is anchored on `html[data-app="ios"]` — specificity
(0,1,1) — so it outranks the bare `body` / `:root` rules in the component
sheet and in `engine/pwa.py`'s safe-area layer whatever order the layers
are concatenated in, and it can never fire outside the app.

## What does not change

Everything else. Cards, tables (their sticky column headers still pin at
`top: 0`), bottom sheets, popovers, the legend, the quiet-mode notice, the
offline banner, the Set-lineup deep links — all render exactly as in a
browser. **The header and tab markup is still emitted**; only its display
changes. One HTML file serves a browser tab, the installed web app and the
native app, and the publish pipeline does not fork.

## What the native app provides instead

| The page's shell used to give…      | The app now gives…                                           |
|-------------------------------------|--------------------------------------------------------------|
| wordmark + league switcher + `WK n` | its own header: brand, league switcher, week                 |
| nav links / five phone tabs         | its own tab bar: Home, Lineup, Board, Ledger, Trade          |
| Light / Dark toggle                 | stamps `data-theme` to the phone's appearance, and re-sets it live when the appearance changes |
| preferences gear (theme, density, type, inbox, quiet) | its Settings screen, written as the same attributes |

## Theme and preferences still apply — driven by the app

`engine/prefs.py`'s CSS keys on attributes of `<html>`, not on the gear, so
the whole preferences layer keeps working. The native app drives it by
setting, on the same element — in the served markup for the first paint,
or on the live document afterwards:

```
data-theme="light" | "dark" | "broadcast"   (absent = follow the OS)
data-density="compact"                       (absent = comfortable)
data-type="large"                            (absent = default)
data-quiet="1"                               (absent = quiet mode off)
data-inbox="top"                             (absent = side; home page only)
```

An app-set `data-theme="dark"` paints exactly the tokens the toggle's
`:root[data-theme="dark"]` block paints — the three theme states in
`engine/ui.py` are unchanged. With no `data-theme` at all the page follows
`prefers-color-scheme`, which `WKWebView` reports from the system. Today
the app stamps `data-theme="light|dark"` from the phone's appearance on
every page it serves and re-sets it on the live document when the
appearance changes; the page repaints without a reload, because the theme
is CSS keyed on that attribute and nothing else.

**In app mode the page's own scripts neither read nor write those
attributes from storage.** Two scripts used to:

* the theme toggle's script (`ui.theme_toggle()`) read `localStorage
  ["wr-theme"]` and wrote it onto `data-theme`;
* the preferences boot script (`prefs.boot_js()`) read
  `localStorage["wr-prefs"]`, applied all five attributes — **removing**
  any it had no stored value for — and folded later `data-theme` changes
  back into storage.

Both now return at once when `data-app` is present on `<html>`. Without
the guard, an app that set `data-theme="dark"` at document start would
have had it stripped by the boot script's "no preference stored → remove
the attribute" step, and a theme stored in some earlier session would
have painted over whatever the app chose. The guard checks the attribute
by presence, so the app is the single owner of the attributes for the life
of the document. (Outside app mode nothing changed: a stored theme still
lands before first paint, the gear still works — `tests/prefs_test.py`
keeps a control case for exactly that.)

## Checking it by hand

Open any rendered page in a desktop browser, then in the console:

```js
document.documentElement.setAttribute("data-app", "ios")
```

The header and tab bar vanish and the first card moves to the top; remove
the attribute and they return. Set `data-theme="dark"` beside it and the
page re-themes with no toggle in sight.
