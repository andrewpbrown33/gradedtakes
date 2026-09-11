# Obsidian Glass — theme spec for the Graded Takes iPhone view

Status: design spec, not wired. Nothing under `engine/` or `ios/` was touched. Companion files in this folder: `mockups.html` (ten frames on one sheet, judge by feel), `RATIONALE.md` (why), `BRIEF-dark-glass.md` and `liquid-glass-brief.md` (the research this stands on), `tokens.obsidian.css` / `.json` (§1 and §4.2 of this spec verbatim, in the live `--wr-*` vocabulary — synced 2026-09-10; if they ever disagree with this file, this file wins). The Model page (frame e) is drawn from `design/model/BRIEF.md` §2.

The one-sentence version: **the chrome is Apple's Liquid Glass, the page is smoked glass, and gold is spent once.** Gold *text* is for numbers and times only (§5.6). Two native glass bars float over a transparent web view; the native shell paints the obsidian ground behind it; the page's cards are translucent panels with a lit top edge (no blur); at most one page strip per screen may blur; verdicts stay weight-encoded; the honesty banner is the one opaque thing on the chrome.

---

## 0. The decisions, and the one deviation from the brief-as-worded

| Decision | Choice |
|---|---|
| Ground | `#0A0C12` obsidian (cool near-black, the navy's hue at L\* 3.4), painted **natively** with a slow ramp and two soft lights so the glass has something to refract. The page paints nothing. |
| Chrome | Two real Liquid Glass bars (`safeAreaBar` top and bottom, one `GlassEffectContainer` each), monochrome glyphs, `.tint(gold)` as the single tint. iOS 26+; iOS 17–25 keep today's navy bars. |
| Page cards | **Translucent, not blurred**: `rgba(18,21,29,.78)` + 1px hairline + 1px inset top highlight. This reads as smoked glass over the native ground, costs nothing, and obeys "Don't use Liquid Glass in the content layer." |
| Page floats | At most **two** `backdrop-filter` surfaces per screen, each a floating control, never a card: the bottom accessory strip ("Next lock" on Home, the primary verb on Lineup) and, if it ever floats, the lock/honesty strip. In Shape B these are native glass anyway. |
| Verdicts | Unchanged in meaning, tuned for dark: gold fill = START, hairline ghost-glass = SIT, dashed gold = TOSS-UP. |
| Gold budget | START fills + one primary verb per screen; the attention rule (Needs-you card, honesty banner, your column on the Trade Desk, the creator ring); gold *text* only on numbers and times that carry a decision — `WK 1`, the lock time, the banner's date (§5.6). Never on a word: kickers, SMASH, VS, SPLIT, NEEDS YOU, DO NOW, "6 calls", "wt" are cream or dim. The floating strip carries **no** gold rule — it is already the float. |
| Fifth tab | Drawn as **Model** (proposed by `design/model/BRIEF.md`, replacing Ledger); the Ledger frame (f) shows the alternative with Ledger in the fifth slot. The owner's call (§12). |
| Honesty banner | Opaque `wash-hot` strip with a 2px gold rule, docked under the top bar, pushes content — the one deliberately non-glass element in the chrome. |
| Reduce Transparency | System frosts the bars; shell makes the web view opaque; page cards and floats go solid `panel`. Frame (j) in the mockups. |

**The deviation.** The ask says "cards as translucent panels with backdrop-filter and the 1px edge highlight." Both research briefs, Apple's HIG ("Don't use Liquid Glass in the content layer… always avoid glass on glass") and the performance envelope on A13–A15 say the *blur* is the part that should not be there. Translucency does the visual work; blur exists to make *content underneath* legible, and the ground has no content. So: cards are translucent with the edge highlight, and **not blurred**. `mockups.html` has a checkbox ("Blur the content cards too") that adds `backdrop-filter: blur(16px)` to every card so the owner can judge the difference by eye rather than take this on trust. If the owner prefers the blurred version, the CSS is one rule (`.blur-cards .card` in the mockup) and the Reduce-Transparency fallback is already written for it.

---

## 1. Tokens

Same key set as `_BROADCAST` in `engine/prefs.py`, plus four new names (`raised-2`, `nav-text-2`, `frost`, and the `gt-*` glass knobs). Contrast is WCAG 2.x relative luminance; alpha tokens are resolved over `canvas`. Hue and saturation are HSV; the hue rule (§1.1) is proven per row.

| Token | Hex | Hue° / sat · hue rule | vs canvas | vs panel | vs raised | Role |
|---|---|---|---|---|---|---|
| `canvas` | `#0A0C12` | 225° / 0.44 · ok | — | 1.1 | 1.2 | the ground; L\* 3.4, cool cast (the navy's hue at near-black); never `#000` |
| `panel` | `#12151D` | 224° / 0.38 · ok | 1.1 | — | 1.1 | content card fill (opaque form; app mode uses it at 78%) |
| `raised` | `#1C202B` | 224° / 0.35 · ok | 1.2 | 1.1 | — | pills, badges, ghost verbs, avatar discs, secondary controls |
| `raised-2` | `#262A35` | 224° / 0.28 · ok | 1.4 | 1.3 | 1.1 | the selected segment (new) |
| `hairline` | `#FFFFFF14` | 225° / 0.20 · ok | 1.2 | 1.1 | 1.0 | card edge, row dividers (white 8%) |
| `hairline-2` | `#FFFFFF24` | 225° / 0.13 · ok | 1.4 | 1.4 | 1.2 | pill borders, group dividers (white 14%) |
| `text` | `#E8E3D8` | 41° / 0.07 · ok | **15.3** | **14.3** | **12.7** | primary ink, warm off-white; never `#FFF` |
| `muted` | `#ABA9A1` | 48° / 0.06 · ok | **8.3** | **7.8** | **6.9** | secondary ink (ledes, reasons, sub-lines) |
| `dim` | `#909298` | 225° / 0.05 · ok | **6.3** | **5.9** | **5.2** | tertiary ink (labels, times, non-gold kickers) |
| `nav-text-2` | `#C9C5BC` | 42° / 0.06 · ok | **11.4** | **10.6** | **9.4** | the only secondary ink allowed on glass: the status line under the league (new) |
| `gold` | `#F2B722` | 43° / 0.86 · ok | **10.8** | **10.1** | **9.0** | the one accent: START fill, the primary verb, rules, gold numerals |
| `rule` | `#F2B722` | 43° / 0.86 · ok | 10.8 | 10.1 | 9.0 | the attention rule (same hex as gold on obsidian; on paper it is not) |
| `chip-ink` | `#101B33` | 221° / 0.69 · ok | — | — | — | navy ink on every gold fill (**9.4** on gold); the navy survives here and under the mark |
| `chip-start` | `#F2B722` | 43° / 0.86 · ok | 10.8 | 10.1 | 9.0 | START = solid fill |
| `chip-sit` | `#6A6E77` | 222° / 0.11 · ok | 3.8 | 3.6 | 3.2 | SIT = hairline outline; meets the 3:1 non-text floor on every surface it sits on (3.4 on the translucent card; 2.8 on `raised-2`, where a chip never sits) |
| `chip-lean` | `#F2B722` | 43° / 0.86 · ok | 10.8 | 10.1 | 9.0 | TOSS-UP = dashed gold |
| `chip-none` | `#3C3F49` | 226° / 0.18 · ok | 1.9 | 1.7 | 1.5 | no verdict; deliberately recessive (not a control) |
| `mint` | `#9DBBF3` | 219° / 0.35 · ok | 10.1 | 9.4 | 8.4 | "positive" = ink-blue, never green |
| `coral` | `#BDB0A0` | 33° / 0.15 · ok | 9.2 | 8.6 | 7.7 | "negative" = stone, never red |
| `wash-hot` | `#2D281E` | 40° / 0.33 · ok | 1.3 | 1.2 | 1.1 | the honesty banner, the empty-record note (text 11.5, muted 6.2, gold 8.1 on it) |
| `wash-split` | `#24221D` | 43° / 0.19 · ok | 1.2 | 1.1 | 1.0 | the challenger line under a contested slot (muted 6.8 on it) |
| `wash-cold` | `#1B1E26` | 224° / 0.29 · ok | 1.2 | 1.1 | 1.0 | cold/bye rows |
| `wash-good` | `#141E32` | 220° / 0.60 · ok | 1.2 | 1.1 | 1.0 | good-matchup rows |
| `wash-bad` | `#212125` | 240° / 0.11 · ok | 1.2 | 1.1 | 1.0 | avoid rows |
| `shadow` | `#0000009E` | — · ok | — | — | — | drop shadow under floating glass only; never under a card |
| `nav` | `#0E1118` | 222° / 0.42 · ok | 1.0 | 1.0 | 1.2 | glass base colour; opaque web-header fallback outside the app |
| `nav-raised` | `#21242A` | 220° / 0.21 · ok | 1.3 | 1.2 | 1.0 | web-header selected segment (fallback) |
| `nav-line` | `#303238` | 225° / 0.14 · ok | 1.5 | 1.4 | 1.3 | web-header hairline (fallback) |
| `meter-hi` | `#F2B722` | 43° / 0.86 · ok | 10.8 | 10.1 | 9.0 | smash/good pips |
| `meter-mid` | `#E8E3D8` | 41° / 0.07 · ok | 15.3 | 14.3 | 12.7 | neutral pips |
| `meter-lo` | `#3A3E48` | 223° / 0.19 · ok | 1.8 | 1.7 | 1.5 | OFF pips (drawn at 45%); the ON pips of a tough/avoid meter use `dim` (obsidian override) |
| `frost` | `#14171E` | 222° / 0.33 · ok | 1.1 | 1.0 | 1.1 | Reduce-Transparency bar fill at 96% (new) |

Glass knobs (not colours the reader sees; the recipe in §3 and §4):

| Knob | Value | Used by |
|---|---|---|
| `gt-glass-fill` | `rgba(28,31,40,.52)` | the mockup's stand-in for Apple's regular dark glass; native code does not set this |
| `gt-float-fill` / `gt-float-blur` | `rgba(14,17,24,.72)` / `20px` | a page-rendered L2 float (web fallback of the accessory) |
| `gt-panel-fill` | `rgba(18,21,29,.78)` | the translucent content card in app mode |
| `gt-edge-top` / `gt-edge` | white 16–18% / white 7% | the lit top edge and the faint all-round rim |
| `gt-shadow` | `0 8px 24px rgba(0,0,0,.45)` | under floats only |

### 1.1 The hue rule, proven

No green, no red, anywhere. Every colour in the theme and in `mockups.html` (39 distinct values including the wallpaper lights and the keyboard) was scanned: a colour counts as green if its hue is 70–170° with saturation ≥ 0.08, red if hue < 20° or > 340° with saturation ≥ 0.08. **Zero flags.** The whole palette lives in two bands: cool 219–240° (the obsidian ladder, navy ink, ink-blue `mint`) and warm 33–48° (gold, the cream inks, the stone `coral`, the washes). "Positive" is ink-blue, "negative" is stone, attention is gold, and every verdict is a *weight*, so nothing on the screen can be read as a traffic light. The scan is in the scratch script that built the mockup; rerun it on any token edit.

### 1.2 The ground

Painted natively behind the transparent web view — this is the "app background" the HIG hands to standard materials, and it is what the glass bars refract.

```
vertical ramp   #0A0C12 → #0D1018 (at 55%) → #0A0C12
light 1         radial, 62%×38% at (16%, 10%): rgb(86,102,148) at 34% → 0    (cool, hue 224°)
light 2         radial, 48%×30% at (88%, 26%): gold #F2B722 at 13% → 0        (warm)
light 3         radial, 90%×40% at (55%, 104%): rgb(120,132,168) at 18% → 0   (cool)
diagonal        160°: white 4% → 0 at 38% … 0 at 62% → white 3%
```

The brightest point any text can sit on is under light 1: `#2A3145` (L 0.028). Everything in §11 is computed against that point, not against `#0A0C12`, so the numbers hold at the worst pixel, not the average one. If the ground is ever made brighter than that, rerun the numbers. Reduce Transparency flattens the ground to `#0A0C12` (the shell makes the web view opaque).

---

## 2. Layers — where glass is, and where it is not

Three levels, never more on one screen; a glass element never contains another glass element.

| Level | What | Surface | Blur |
|---|---|---|---|
| 0 | the ground | native obsidian (§1.2) | — |
| 1 | content | translucent card `rgba(18,21,29,.78)`, hairline, 1px inset top highlight white 6%, **no drop shadow** | none |
| 1+ | raised-in-content | `raised` / `raised-2` opaque: pills, badges, ghost verbs, avatar discs, segmented control | none |
| 2 | floating over content | native Liquid Glass: top bar, tab bar, bottom accessory strip; web fallback `.gt-glass` at 72% | Apple's / 20px |
| 3 | modal | system sheets and menus (Apple's material); their *contents* are Level 1 panels | Apple's |

| Screen element | Layer | Glass? |
|---|---|---|
| Top bar: mark, league switcher + status line, week badge, share, settings | navigation | **yes** — native |
| Tab bar (Home / Lineup / Board / **Model** or Ledger / Trade Desk) | navigation | **yes** — native; selection = a white-8% fill on the glass, the glyph takes the tint, the label stays primary ink |
| Bottom accessory: "Next lock" strip (Home), the primary verb (Lineup) | floating control | **yes** — native in Shape B; `.gt-glass` if the page renders it |
| Honesty banner | chrome, transient | **no** — opaque `wash-hot`, gold rule (§6) |
| Sheets (settings, share, league picker menu) | modal | yes — system |
| Needs-you inbox, groups, items, verb buttons | content | no |
| Roster rows, status pills, opponent chips, projections, verdict chips | content | no |
| Lineup slots, challenger lines | content | no |
| Decision Cards (versus and compact), Agree / Override | content | no |
| Ledger digest, Trade Desk grid (stacked, your column first) and needs matrix (8 × 4 meters at 390) | content | no |
| Model: share bar, Your-sources rows, switches, sliders, library cards, suggestion rows, receipts | content | no — switches and slider thumbs are cream on obsidian (the one tint would put eight gold switches on a page) |
| Model: the search box | control in content | no — 5% white fill, hairline-2 |
| Sources nameplates, avatars, sparklines | content | no |
| Segmented filter on the Board | control in content | no — `raised` fill; the HIG glass exception is only for transient activation of sliders/toggles |
| Onboarding: Paste button | native control | yes — `.buttonStyle(.glass)` |
| Onboarding: "Open your week" | the primary verb | yes — `.glassProminent` tinted gold |

---

## 3. Native recipe (SwiftUI, iOS 26+)

Shape B from the technical brief: one `WKWebView`, two custom glass bars. Everything below sits behind `if #available(iOS 26, *)`; the iOS 17–25 branch keeps today's navy `HStack` bars unchanged.

```swift
// Host (MainView, iOS 26 branch)
WebView(…)                                   // isOpaque = false, clear backgrounds (§4.1)
    .background { ObsidianGround() }         // §1.2, .ignoresSafeArea()
    .safeAreaBar(edge: .top)    { ObsidianTopBar(banner: bannerState) }
    .safeAreaBar(edge: .bottom) { ObsidianBottomBar(accessory: accessory, selected: $router.destination) }
    .tint(Brand.gold)                        // the ONE tint: tab selection + glassProminent
    .preferredColorScheme(.dark)             // Obsidian is dark-only (HIG's "rare case"; the app is one room)
```

```swift
@available(iOS 26, *)
struct ObsidianTopBar: View {
    @Namespace private var ns
    var body: some View {
        VStack(spacing: 6) {
            GlassEffectContainer(spacing: 8) {
                HStack(spacing: 8) {
                    DiamondMark(size: 14)                                   // the mark, content on glass
                        .frame(width: 44, height: 44)
                        .glassEffect(.regular, in: .capsule)
                    Menu { leaguePicker } label: {                          // league = the page title, status = subtitle
                        VStack(alignment: .leading, spacing: 1) {
                            Label(league, systemImage: "chevron.down").labelStyle(.titleAndIcon)
                                .font(.system(size: 15, weight: .semibold))
                            Text(statusLine)                                // "Live · checked 9:04 PM" / "Saved copy · Thu 9:04 PM"
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(Brand.obsidianNavText2)    // #C9C5BC — the only secondary ink on glass
                                .lineLimit(1).truncationMode(.tail)
                        }
                        .padding(.horizontal, 12).frame(height: 44)
                    }
                    .buttonStyle(.glass)
                    Text("WK \(week)")                                      // gold TEXT, not a gold fill
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(Brand.gold)
                        .padding(.horizontal, 9).frame(height: 44)
                        .glassEffect(.regular, in: .capsule)
                    HStack(spacing: 0) {
                        Button { share() } label: { Image(systemName: "square.and.arrow.up").frame(width: 44, height: 44) }
                        Button { settings() } label: { Image(systemName: "gearshape").frame(width: 44, height: 44) }
                    }
                    .buttonStyle(.plain)
                    .glassEffect(.regular, in: .capsule)                    // one capsule, two glyphs
                }
                .padding(.horizontal, 12)
            }
            if let banner { OfflineBanner(state: banner) { reload() } }     // OPAQUE, §6 — inside the bar so it pushes content
        }
    }
}
```

```swift
@available(iOS 26, *)
struct ObsidianBottomBar: View {
    var body: some View {
        GlassEffectContainer(spacing: 8) {
            VStack(spacing: 8) {
                if let accessory {                                          // "Next lock …" or the page's primary verb
                    accessory                                               // cream text, gold only on the time; NO gold rule -
                        .frame(height: 46)                                  // it is already the float, and a rule on it samples as a gold-tinted bar
                        .glassEffect(.regular, in: .rect(cornerRadius: 15))
                }
                HStack(spacing: 0) {
                    ForEach(Destination.allCases) { d in
                        let on = selected == d
                        Button { select(d) } label: {
                            VStack(spacing: 2) {
                                Image(systemName: d.symbol).font(.system(size: 22, weight: .regular))
                                Text(d.title).font(.system(size: 11, weight: on ? .semibold : .medium))
                            }
                            .frame(maxWidth: .infinity, minHeight: 50)
                            .foregroundStyle(.primary)                      // the LABEL stays primary ink: 9.0:1 on the pill (gold on the pill was 4.9:1)
                            .symbolRenderingMode(.monochrome)
                            .tint(on ? Brand.gold : nil)                    // the GLYPH takes the tint: 6.3:1 non-text on the pill
                            .background {                                   // selection = a FILL on the glass, never glass on glass
                                if on { Capsule().fill(.white.opacity(0.08)) }
                            }
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(on ? [.isSelected] : [])
                    }
                }
                .padding(4)
                .glassEffect(.regular.interactive(), in: .capsule)
            }
            .padding(.horizontal, 14)
        }
    }
}
```

Rules that go with the code:

- **Never paint the bars.** No `.background(Brand.navy)`, no `UIBarAppearance`. The glass is the background. (Apple: "Reduce your use of custom backgrounds in controls and navigation elements.")
- **Regular glass everywhere.** `.clear` needs a dimming layer and is for media; this is a text app.
- **The scroll edge effect is load-bearing, not decoration.** With `safeAreaBar` the system extends the web view's scroll edge effect under the bars; keep `.scrollEdgeEffectStyle(.soft, for: .top)` and `.bottom`. The maths: cream text on bare 52% glass directly over a START chip is **4.14:1 (fails)**; with the edge dim beneath it is **8.64:1**. The bar is only legible because the edge effect is there.
- **Text on glass** is `.primary` / vibrant system label, or `text` `#E8E3D8`; the one secondary is `nav-text-2` `#C9C5BC` (8.6:1 on the worst-case glass). No `muted`, no `dim` on Level 2.
- **One tint.** `.tint(Brand.gold)` colours the selected tab's glyph and any `.glassProminent` verb. Do not `.tint` the bar glass, the accessory, the WK capsule, or the selected tab's label.
- **The wordmark yields.** At 390pt five capsules do not fit; the diamond carries the identity and the league is the title, with the honesty status as its subtitle (Apple's own title/subtitle idiom). "GRADED TAKES" lives on Onboarding, Settings and the icon. Every tab-bar frame shows the result.
- **Tab labels are 11pt** (the product floor), one point above `MainView`'s current 10.
- **Sheets** stay system `.sheet` — they get the material for free. Their contents are Level 1 panels, not glass.
- **Onboarding** (native): `PasteButton` → `.buttonStyle(.glass)`; "Open your week" → `.buttonStyle(.glassProminent)` with the gold tint (the screen's one gold verb); the field is a translucent panel with a 1.5pt gold stroke when focused; the 40×3 gold rule stays.

---

## 4. Web-side treatment in app mode

### 4.1 Shell side (observed in `ios/`, not edited)

`WebView.swift`: `isOpaque = false`, `backgroundColor = .clear`, `scrollView.backgroundColor = .clear`, `underPageBackgroundColor = .clear`; `contentInsetAdjustmentBehavior = .automatic` so `safeAreaBar` insets reach the page as `env(safe-area-inset-*)`. Under Reduce Transparency: `isOpaque = true`, `backgroundColor = obsidian`. Inject at document start, alongside `data-app` and `data-theme`: `data-theme="obsidian"`, `data-reduce-transparency="0|1"`, `data-increase-contrast="0|1"` (WebKit has no `prefers-reduced-transparency`).

### 4.2 Page side

```css
:root[data-theme="obsidian"] { /* the token block: tokens.obsidian.css + raised-2, nav-text-2, frost */ }

/* app mode: the page paints no ground; the native shell does */
html[data-app="ios"][data-theme="obsidian"], html[data-app="ios"][data-theme="obsidian"] body { background: transparent; }
html[data-app="ios"] body { padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom); }  /* safeAreaBar extends these */

/* LEVEL 1 - the content card: translucent fill + lit edge. No blur. No drop shadow. */
[data-theme="obsidian"] .wr-card {
  background: var(--gt-panel-fill);                 /* rgba(18,21,29,.78) */
  border: 1px solid var(--wr-hairline);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.06);
  border-radius: 14px;
}
[data-theme="obsidian"] .wr-card.wr-attn { box-shadow: inset 0 2px 0 var(--wr-rule), inset 0 1px 0 rgba(255,255,255,.06); }

/* LEVEL 2 - the page-rendered float (only when the shell does not render it natively). Max two per screen. */
.gt-glass { background: var(--gt-float-fill); -webkit-backdrop-filter: blur(20px) saturate(140%); backdrop-filter: blur(20px) saturate(140%);
            border: 1px solid rgba(255,255,255,.07);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.16), inset 0 -1px 0 rgba(0,0,0,.35), 0 8px 24px rgba(0,0,0,.45); border-radius: 16px; }
.gt-glass.gt-attn { box-shadow: inset 0 2px 0 var(--wr-rule), inset 0 -1px 0 rgba(0,0,0,.35), 0 8px 24px rgba(0,0,0,.45); }
.gt-glass:active { box-shadow: inset 0 0 0 999px rgba(255,255,255,.06), inset 0 1px 0 rgba(255,255,255,.16); }  /* pressed = lit from within */

/* Reduce Transparency (injected) and Increase Contrast (native media query + injected): solid obsidian panels */
:root[data-reduce-transparency="1"] .wr-card, :root[data-increase-contrast="1"] .wr-card { background: var(--wr-panel); }
:root[data-reduce-transparency="1"] .gt-glass, :root[data-increase-contrast="1"] .gt-glass {
  background: var(--wr-panel); -webkit-backdrop-filter: none; backdrop-filter: none; border: 1px solid var(--wr-hairline-2); }
@media (prefers-contrast: more) {
  :root[data-theme="obsidian"] { --wr-muted: #C4C2BA; --wr-dim: #ABADB3; --wr-chip-sit: #8E929B; }
  [data-theme="obsidian"] .wr-card { background: var(--wr-panel); border-color: rgba(255,255,255,.5); }
}
@media (prefers-reduced-motion: reduce) { .gt-glass { transition: none; } }
```

Obsidian-specific component overrides (all colour, no markup change):

```css
/* the slot / position badge is plain dim mono - un-boxed; the row is not a form */
[data-theme="obsidian"] .wr-pos { background: transparent; border: 0; color: var(--wr-dim); letter-spacing: 0.06em; }
/* opponent chips carry no gold: only a GRADED opponent carries weight (§5.3) */
[data-theme="obsidian"] .wr-opp { border-color: transparent; color: var(--wr-muted); }
[data-theme="obsidian"] .wr-opp-none { color: var(--wr-dim); border-style: solid; }
[data-theme="obsidian"] .wr-opp-good, [data-theme="obsidian"] .wr-opp-tough { border-color: rgba(232, 227, 216, .55); color: var(--wr-text); }
[data-theme="obsidian"] .wr-opp-smash { background: transparent; color: var(--wr-text); border: 1.5px solid var(--wr-text); }
[data-theme="obsidian"] .wr-opp-avoid { background: var(--wr-text); color: var(--wr-panel); border-color: var(--wr-text); }
/* a wall is drawn in dim ink, not in the OFF colour; the meter LABEL is cream, never gold - the pips say SMASH once */
[data-theme="obsidian"] .wr-meter-lo .wr-meter-on { fill: var(--wr-dim); }
[data-theme="obsidian"] .wr-meter-hi .wr-meter-l { color: var(--wr-text); }
/* in a row the confidence rides BESIDE the verdict chip in dim mono; a locked player never gets a fill */
[data-theme="obsidian"] .wr-chip-md .wr-chip-pct { color: var(--wr-dim); background: transparent; }
[data-theme="obsidian"] .wr-chip-locked { background: transparent; border-color: transparent; color: var(--wr-dim); font-weight: 600; }
/* gold TEXT is for numbers and times only (§5.6) */
[data-theme="obsidian"] .wr-kicker { color: var(--wr-muted); }
[data-theme="obsidian"] .wr-np-w { color: var(--wr-dim); }
/* avatars lift off the card on the raised step; the 2px gap ring is solid panel so it reads over the translucent card */
[data-theme="obsidian"] .wr-av { background: var(--wr-raised); box-shadow: 0 0 0 2px var(--wr-panel), 0 0 0 3.5px var(--wr-hairline-2); }
[data-theme="obsidian"] .wr-av-creator { box-shadow: 0 0 0 2px var(--wr-panel), 0 0 0 3.5px var(--wr-rule); }
/* SIT = ghost glass: hairline outline, a 3% white fill, muted ink */
[data-theme="obsidian"] .wr-chip-sit { background: rgba(255,255,255,.03); color: var(--wr-muted); border-color: var(--wr-chip-sit); }
/* verbs: capsules, 44px tall; one primary per screen */
[data-theme="obsidian"] .wr-verb { min-height: 44px; border-radius: 22px; background: var(--wr-raised); color: var(--wr-text);
                                    border: 1px solid var(--wr-hairline-2); box-shadow: inset 0 1px 0 rgba(255,255,255,.05); }
[data-theme="obsidian"] .wr-verb-primary { background: var(--wr-chip-start); color: var(--wr-chip-ink); border-color: var(--wr-chip-start); }
```

Row layout at phone width (`row3`): identity and the verdict chip on line one, context (opponent chip · kickoff · meter · projection) on line two. Same three semantic columns, wrapped; rows are 54–58px, the row is the tap target. The lineup page's badge is the *slot* (`FLEX2`, plain dim mono, un-boxed); the position rides **before** the team code and only where the slot does not imply it (`RB·PIT` on a flex slot, `DET` on `RB1`) — never `NO RB`, which reads as "no running back". The confidence sits beside the chip in dim mono (`[START] 83%`). The challenger line sits under the row on `wash-split` with a dim `VS` kicker, the challenger's median, the graded opponent chip and the meter — the old `100·0` split readout is gone (the pips and the one-line reason already say it).

Sticky table heads inside cards (`.wr-table th`) keep `background: var(--wr-panel)` opaque — a translucent sticky header over rows is glass on content.

---

## 5. Verdicts, pills, chips, meter, faces

### 5.1 Verdict encoding on dark (weight, never hue)

| Verdict | Treatment | Ink | Proven |
|---|---|---|---|
| **START** | solid gold fill `#F2B722`, 6px radius; the word only — in a row the confidence sits **beside** the chip in `dim` mono (5.9:1); the versus card's large chip keeps it inside | `chip-ink` navy | 9.4:1; the in-chip `%` at 82% navy is 6.6:1 |
| **SIT** | ghost glass: 1px `#6A6E77` outline + white 3% fill | `muted` | 6.8:1 on the worst-case card; the outline is 3.4:1 (non-text floor 3:1); `%` at 82% is 5.0:1 |
| **TOSS-UP** | 1px dashed gold, no fill | `gold` | 9.5:1; `%` at 82% is 6.7:1 |
| none / unfiled / **Locked** / "contests FLEX" | no border, no fill — a locked player never gets a verdict fill, on Home or on Lineup | `dim`, 600 weight | 5.5:1 |

The START fill does not change with the theme (it is the board's language). On obsidian it is the brightest object on the screen, which is correct for the one thing the page exists to say.

### 5.2 Status pills (weight, never hue)

| Codes | Weight | Treatment |
|---|---|---|
| Q, D | rule | panel fill, hairline-2 border, 3px gold inset left rule, `text` ink |
| O, IR, SUSP | fill | `text` cream fill, `panel` ink (14.3:1) — the only cream block in the system, 18px tall |
| BYE, LOCK | ghost | transparent, hairline-2 border, `dim` ink |

### 5.3 Opponent chips

vs/@ + code, 20px tall, 11px bold. **Only a graded opponent carries weight, and no opponent chip carries gold** (the meter beside it says the grade once): **smash** = 1.5px cream outline, cream text · **good** / **tough** = 1px cream outline at 55%, cream text · **neutral** = borderless, `muted` text · **none** = borderless, `dim` text · **avoid** = cream fill, panel ink, wall glyph. Magnitude is the outline weight; direction is the meter's pips and label (and the wall). The old 2px gold smash outline said SMASH twice per row and put a second gold on every contested line.

### 5.4 Matchup meter

Five 6×13 pips, 2px gap, filled from the left. ON pips: gold for smash/good, cream for neutral, `dim` for tough/avoid (obsidian override — a wall drawn in the OFF colour vanished). OFF pips `meter-lo` at 45%. Label 11px 700, 0.08em: **cream** for smash/good/neutral, `muted` for tough/avoid — the label is a word, so it is never gold; the pips carry the gold. "—" in dim when no read exists (K and D/ST).

### 5.5 Sources are faces

Avatar disc on `raised`, monogram in `text` at 11–12px 700 (12.7:1). Rings: 2px `panel` gap + 1.5px `hairline-2` for a feed; 2px `panel` gap + 1.5px **gold** for a creator (a human voice) — the one gold ring rule survives from the current system; feeds never get it. Nameplate: name 13px 700 (wraps to two lines rather than truncating a creator's name), `wt 17` in **dim** mono (a setting, not a decision — it was gold and pulled the eye to the wrong number), state as a ghost pill (`NO-DATA`), headline in 17px mono (`63%`, or a dim `—`), sub in muted 11px, sparkline in `muted` with a gold end-dot, the empty series as a dashed `hairline-2` line (not a flat one), facts line in muted 11px mono — and no two facts lines alike: the real week-1 numbers differ by `n`, unscorable count and per-position split even where the headline ties at 63%.

### 5.6 Gold text — the rule, exactly

Gold text is allowed on **numbers and times that carry a decision**, and on nothing else:

- allowed: `WK 1`; the lock time in the floating strip and the Lineup lede; the honesty banner's date; the challenger's margin when it decides a slot.
- **never**: kickers (`NEEDS YOU`, `THE BOARD · WEEK 1`), group heads (`DO NOW`), meter labels (`SMASH`), the challenger's `VS`, the `SPLIT` tag, the segmented control's counts, `6 calls`, `4 contested`, `wt 17`, `n 2264`, projections, shares on the Model page. These are all cream or dim.

The test: if the word would still be true printed in grey, it is grey. Gold on a numeral is spent, not sprinkled.

---

## 6. The honesty banner on glass

State → copy is `BannerState.make` today and does not change. Placement and look:

- Docked **inside the top `safeAreaBar`**, under the capsules, full width minus 12pt margins, 14pt radius. Because it is in the bar it insets the page — it pushes content, it never floats over it and it can never be scrolled away.
- **Opaque** `wash-hot` `#2D281E`. It does not take the glass material: a translucent warning over moving content is a quieter warning. On a screen where everything else is glass, the one solid warm strip is the loudest thing without being a colour.
- 2px gold rule along the top (inset), title 13pt semibold in `text` (11.5:1), the date in gold mono (8.1:1), detail 11pt in `text` (9.9:1 at 92%), Retry as a 44pt gold-outline capsule with gold text — an outline, so the gold *fill* budget stays at one verb.
- The status line under the league title says the same thing in three words ("Saved copy · Thu 9:04 PM"), so the honesty is stated twice: once on glass, once in the strip.
- Reduce Transparency changes nothing about it (frames c and j).

---

## 7. Typography — unchanged

Archivo (UI), Archivo Black (display: h1, the START/SIT words on the versus card), Spline Sans Mono (every number, time, percentage, weight, `n`). Scale `t0 26 · t1 17 · t2 15 · t3 13 · t4 11`; 11px is the floor and nothing in the mockup is under it (DOM-audited). Native chrome uses SF: 15 semibold league title, 11 medium subtitle, 11 bold mono `WK 1`, 11 tab labels, 17 semibold status-bar time; onboarding title2 22 semibold, body 17, footnote 13. Numbers in native chrome use `.monospaced` design. Tabular figures everywhere.

---

## 8. Motion — minimal

- The bars do not minimise on scroll (Shape B has no automatic minimise; do not fake one).
- The scroll edge effect is the only thing that "moves" with scroll: content blurs and dims as it passes under the bars (`.soft`). Reduce Motion: Apple disables the elastic properties; nothing else to do.
- The bottom accessory appears when it has something to say (a lock ahead, a verb): 200ms opacity fade, no slide, no morph. Reduce Motion → instant.
- Pressed state on glass = Apple's "illuminate from within" via `.interactive()`; on the web float, an inset 6% white lift. No glow, ever.
- Tab change: the selection pill moves with the system's default; content swaps without a page transition (it is one web view).
- League menu, share dialog, settings sheet: system transitions. No custom morphing (`glassEffectID`) anywhere — the app has no transient tool groups to morph.

---

## 9. Accessibility contract

- **Contrast floors**: text ≥ 4.5:1 on every surface it can sit on including the brightest ground pixel and a translucent card over it; secondary ink targets ≥ 7:1 on opaque surfaces (`muted` 7.8 on panel); non-text UI (SIT outline, meter pips) ≥ 3:1. Large bold text (keyboard keys 22px) ≥ 3:1. §11 lists every pair.
- **No meaning by colour alone**: START/SIT/TOSS-UP differ by fill/outline/dash; status by rule/fill/ghost; opponent grade by outline weight; creators by ring. A greyscale print still reads.
- **Reduce Transparency**: native glass frosts itself; the shell makes the web view opaque and injects `data-reduce-transparency="1"`; cards and floats go solid `panel`; the ground flattens to `#0A0C12`. Frame (j).
- **Increase Contrast**: native black/white with border; page gets `prefers-contrast: more` (native) plus the injected attribute → `muted #C4C2BA`, `dim #ABADB3`, `chip-sit #8E929B`, 50% white card borders, solid cards.
- **Reduce Motion**: `prefers-reduced-motion` on the page; system on the bars.
- **Targets**: every control ≥ 44×44pt — verbs, Retry, segments, tab items, the two glyph buttons (44 wide, not 42), "show N more"; non-controls that look like pills ("Locked") are spans, not buttons. DOM-audited in the mockup.
- **Type**: the product's own "Larger" pref (+10%) still applies; the 11px floor never moves; the native chrome respects Dynamic Type via `.font(.system(size:))` scaled by the shell if the owner opts in.
- **VoiceOver**: league capsule announces "League: Kid's Table. Live · checked 9:04 PM"; WK capsule "Week 1"; status pills stay `<abbr>` with the long word; avatars keep `role="img"` + the source name; the empty sparkline is labelled "no weekly series".
- **Honesty**: every degraded state names the moment (§6); the Sources page's "no live record" note keeps its gold rule; "Agree / Override are not wired up yet" stays on the card.

---

## 10. The gold budget, per screen (as mocked)

| Screen | Gold fills | Gold rules / outlines | Gold text |
|---|---|---|---|
| Home / Home scrolled | START chips | Needs-you card rule; TOSS-UP dashes | `WK 1`, the lock time in the strip |
| Lineup | START chips (never on a locked row); **Set lineup on ESPN** (the verb, in the floating strip) | banner rule; Retry outline; smash/good pips | `WK 1`, lock time, the banner's date |
| Board | START chip in the gutter (one card); versus share bar (3px) | — | `WK 1` |
| Model | none (a saved, clean page has no primary verb; **Apply n changes** appears only when dirty) | creator rings | `WK 1` |
| Ledger | START chips in the agreement matrix | red-alert rule | `WK 1` |
| Trade Desk | none | your column's rule (grid + matrix); spare-depth pips | `WK 1` |
| Sources | none | creator rings; the note's rule; sparkline end-dot | `WK 1` |
| Onboarding | **Open your week** | the 40×3 rule; focused field stroke | — |

Never two gold verbs on one screen; never a gold-tinted bar (the floating strip carries no rule); never a gold ring on a feed; never gold on a word.

Measured (saturated-gold pixels, hue 30–55° · sat ≥ .55 · val ≥ .55, per 390×844 frame at 2×): Home 0.2%, Home scrolled 1.8%, Lineup 4.1%, Board 1.4%, Model 0.2%, Ledger 0.1%, Trade Desk 0.3%, Sources 0.3%, Onboarding 2.5%, Home RT 0.6%. Lineup was 6.1% on the same instrument before this pass; what remains is the honesty banner (0.45%) and the one primary verb (1.9%) — both mandated above — plus three START chips and their pips (1.7%, the same content share as Home). If the owner takes §12.4 (verb at the top of the page) the Lineup viewport lands near 2.2%.

## 11. Verification of `mockups.html` (what was checked, and the numbers)

Run against the generated file on 2026-09-10 (ten frames + three below-the-fold strips, headless Chrome at 2× and 4×, the critic's own instruments: `hues.py`, `goldshare.py`, `contrast_px2.py`, extended to thirteen captures).

1. **Hue scan** — 77 distinct colours across `mockups.html`, `tokens.obsidian.css` and `tokens.obsidian.json` (hex and `rgb()`/`rgba()`, wallpaper and keyboard included): **0 green, 0 red**; every chromatic hue sits in 33–43° (gold, cream, stone, washes) or 219–240° (the obsidian ladder, navy ink, ink-blue). Pixel scan of all thirteen captures (5.1 M samples): **0 green pixels**; 2 pixels flagged red at saturation 0.10 on the bezel's antialiased edge — not a colour.
2. **Contrast (pixels)** — every text node's box sampled against the rendered ground beneath it: **975 readable text boxes, 0 below 4.5:1 at the median ground and 0 at the 90th-percentile (worst) ground.** Lowest: 4.80:1 (a dim mono count in an unselected segment). Text boxes passing under a floating bar, the strip or the banner (mid-scroll content, 163 boxes) are excluded — they are the scroll-edge effect working, not text. The selected tab: label 9.0–10.9:1 (cream on the white-8% pill; the gold label on the white-12% pill was 4.87:1), glyph 6.3–7.7:1 (non-text floor 3). The Model page's off row is dimmed by ink (`muted`/`dim`), never by an opacity on text.
3. **Gold share** — §10.
4. **The floating strip** — samples as `#1A1B1E` (hue 225°, obsidian) with the rule off and the float recipe (72%); it sampled as `#2D2925` / warmest `#523E15` (a gold-tinted bar) before.
5. **Type floor** — every text node's computed `font-size` ≥ 11px: **0 under.**
6. **Width** — no element's box extends past its 390px frame; no page `scrollWidth` > 390 on any frame or strip: **0 overflows.** The needs matrix (8 teams × 4 positions) and the league grid stack; nothing scrolls sideways. A 22-character league name (`Sunday Regrets Dynasty`, frame e) ellipsises on one line in the capsule.
7. **Targets** — every `<button>`, switch and slider ≥ 44×44: **0 under** (the accuracy line and the switch draw small and hit 44).
8. **Copy** — second person throughout the Model page and the sheet; the word "my" appears nowhere ("Open your week"); no `NO RB`; no `100·0`.

## 12. Open decisions for the owner

1. **Blurred cards or translucent cards** — toggle it in `mockups.html`; the spec recommends translucent (§0).
2. **The wordmark leaves the header** (§3) — the diamond and the league title carry the bar. Confirm.
3. **Obsidian dark-only** (`preferredColorScheme(.dark)`) or Obsidian as a third `data-theme` beside Daylight/Night/Broadcast that follows the system. The mockups assume dark-only inside the app.
4. **Where the primary verb lives on Lineup** — the floating strip (mocked) versus the top of the page. The strip keeps it reachable while scrolling ten slots; it also means the strip is the second float on that page if the lock strip ever appears too (still within the two-per-screen cap).
5. **Tab label size** 11pt vs Apple's default ~10pt — the product floor says 11.
6. **The fifth tab: Model or Ledger.** `design/model/BRIEF.md` argues Model replaces Ledger (the digest keeps rendering, the Tuesday push deep-links to it, Home gains a "This week's brief" card — drawn on frames a, b, j). The sheet draws Model in the fifth slot on every tab-bar frame and keeps the Ledger reachable as frame f with Ledger in the slot, so the two pages can be compared side by side. Frame h (Sources / Receipts) lights Model because the Receipts fold into that page (brief §2.6); if Ledger keeps the slot, Sources has no tab, as today.
