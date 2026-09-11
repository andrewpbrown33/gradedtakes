# Liquid Glass for the Graded Takes iPhone shell — technical brief

Research date: 2026-09-10. Scope: what Apple actually ships and says (iOS 26 / Xcode 26, with the iOS 27 changes that land in four days), and whether "native glass chrome + transparent WKWebView + CSS backdrop-filter cards" is a sound architecture for the obsidian redesign. Every claim carries a source; sources are numbered in §10.

Nothing under `engine/` or `ios/` was touched. Line references into `ios/` are read-only observations.

---

## 0. Version check (verify before assuming "iOS 26 is current")

| Thing | Status on 2026-09-10 | Source |
|---|---|---|
| Xcode on this Mac | **Xcode 26.6 (17F113)**, iOS 26.5 simulator runtime | `xcodebuild -version` on this machine |
| Xcode 27 | **RC shipped** (Apple publishes "Xcode 27 RC Release Notes") | [A24] |
| iOS 27 | Announced WWDC 2026-06-08; **public release Monday 2026-09-14** (Apple-confirmed, per 9to5Mac) | [T1] |
| App deployment target | `IPHONEOS_DEPLOYMENT_TARGET = 17.0` (`ios/GradedTakes.xcodeproj/project.pbxproj:546`) → every glass API must sit behind `if #available(iOS 26, *)` | repo |
| Liquid Glass API availability | All `glassEffect` / `GlassEffectContainer` / `.glass` button styles / `tabBarMinimizeBehavior` / `scrollEdgeEffectStyle` are **iOS 26.0+** | [A1]–[A12] |
| Opt-out key | `UIDesignRequiresCompatibility` is honoured only when building with the iOS 26 SDK; **"The system ignores this key when you build for iOS 27 or later"** — the moment the project is built with Xcode 27, standard components are glass, no opt-out | [A13] |

What changed after WWDC25 that matters for this design:

- **iOS 26.1 (2025-11-03)** added Settings ▸ Display & Brightness ▸ Liquid Glass with two positions, **Clear** and **Tinted** (Tinted raises opacity for contrast). [T3]
- **iOS 27** replaces the two positions with a **continuous slider** (Settings ▸ Appearance ▸ Liquid Glass; left = clearer, right = more tint/opacity; midpoint = Apple default); it is system-wide and affects third-party apps. [T2]
- **iOS 27** also restyles the material: early-beta observation is that dark-mode glass is "much lighter", the selected tab-bar item background becomes darker instead of lighter, and borders are more defined instead of relying on drop shadows. This is a third-party beta observation, not an Apple statement; treat as "expect the look to shift under you". [T4]
- The HIG "Materials" page itself warns that the regular/clear variants "can differ in response to certain system settings, like if people choose a preferred look for Liquid Glass in their device's settings, or turn on accessibility settings that reduce transparency or increase contrast". [A14]

Consequence for the redesign: **the app does not own the exact look of its glass.** The user owns it via the slider and accessibility settings; iOS 27 re-tunes it. Design to the *rules* (what goes on glass, what stays in the content layer, contrast floors), not to a screenshot of one glass appearance.

---

## 1. SwiftUI: the real APIs

### 1.1 `glassEffect` — declaration and defaults

```swift
// SwiftUI, iOS 26.0+  [A1]
nonisolated func glassEffect(
    _ glass: Glass = .regular,
    in shape: some Shape = DefaultGlassEffectShape()
) -> some View
```

Apple: "When you use this effect, the system: renders a shape anchored behind a view with the Liquid Glass material; applies the foreground effects of Liquid Glass over a view. … SwiftUI uses the `regular` variant by default along with a `Capsule` shape. SwiftUI anchors the Liquid Glass to a view's bounds … the material fills the entirety of the `Text` frame, which includes the padding." [A1]

Note: the `glassEffect(_:in:isEnabled:)` form that early tutorials show **404s on developer.apple.com today**; the shipping signature has no `isEnabled`. To turn glass off conditionally, pass `Glass.identity` ("your content remains unaffected as if no glass effect was applied"). [A2]

### 1.2 `Glass` — variants and modifiers

```swift
struct Glass                              // iOS 26.0+  [A2]
static var regular: Glass                 // "The regular variant of the Liquid Glass material."
static var clear: Glass                   // "The clear variant of glass."
static var identity: Glass                // no-op
func tint(_ color: Color?) -> Glass       // "Returns a copy of the structure with a configured tint color."  [A3]
func interactive(_ isEnabled: Bool = true) -> Glass   // "configured to be interactive"  [A4]
```

Apple's own three-line ladder, verbatim from "Applying Liquid Glass to custom views" [A5]:

```swift
Text("Hello, World!").font(.title).padding()
    .glassEffect()

Text("Hello, World!").font(.title).padding()
    .glassEffect(in: .rect(cornerRadius: 16.0))

Text("Hello, World!").font(.title).padding()
    .glassEffect(.regular.tint(.orange).interactive())
```

And the one rule the `.clear` doc page adds, because clear glass has no adaptive legibility behaviour [A6]:

> "When using clear glass, ensure content remains legible by adding a dimming layer or other treatment beneath the glass."
> ```swift
> Label("Flag", systemImage: "flag.fill")
>     .padding()
>     .glassEffect(.clear)
>     .background(.black.opacity(0.3))
> ```

Ordering rule: "Apply the `glassEffect(_:in:)` modifier after other modifiers that affect the appearance of the view." [A5]

### 1.3 `GlassEffectContainer`, `glassEffectID`, `glassEffectUnion`, transitions

```swift
@MainActor @preconcurrency struct GlassEffectContainer<Content: View>   // iOS 26.0+  [A7]
init(spacing: CGFloat? = nil, content: () -> Content)
```

Why it is not optional when you have more than one glass element: "glass can not sample other glass, so having nearby glass elements in different containers will result in inconsistent behavior. Using a glass container allows these elements to share their sampling region" (WWDC25-323 [W3]); "Use `GlassEffectContainer` when applying Liquid Glass effects on multiple views to achieve the best rendering performance" [A5]; "Combine custom Liquid Glass effects to improve rendering performance … using a `GlassEffectContainer`" [A15].

Spacing semantics: "The larger the spacing value on the container, the sooner the Liquid Glass effects behind views blend together and merge the shapes during a transition. A spacing value on the container that's larger than the spacing of an interior `HStack`, `VStack` … causes Liquid Glass effects to blend together at rest." [A5]

Morphing (Apple's example, abridged) [A5]:

```swift
@State private var isExpanded = false
@Namespace private var namespace

GlassEffectContainer(spacing: 40.0) {
    HStack(spacing: 40.0) {
        Image(systemName: "scribble.variable")
            .frame(width: 80, height: 80).font(.system(size: 36))
            .glassEffect()
            .glassEffectID("pencil", in: namespace)
        if isExpanded {
            Image(systemName: "eraser.fill")
                .frame(width: 80, height: 80).font(.system(size: 36))
                .glassEffect()
                .glassEffectID("eraser", in: namespace)
        }
    }
}
Button("Toggle") { withAnimation { isExpanded.toggle() } }
    .buttonStyle(.glass)
```

- `glassEffectID(_:in:)` — "SwiftUI uses the identifier to animate shapes to and from each other during transitions." [A8]
- `glassEffectUnion(id:namespace:)` — "All Liquid Glass effects with the same shape and Liquid Glass variant will be combined into a single shape." Useful for a segmented pill built from separate buttons. [A9]
- `GlassEffectTransition` — `.identity`, `.matchedGeometry` (default inside container spacing), `.materialize` (fade + animate material, no geometry matching). [A10]

### 1.4 Glass button styles

```swift
Button("Button") {}.buttonStyle(.glass)            // GlassButtonStyle — "applies a Liquid Glass effect based on the button's context"  [A11]
Button("Button") {}.buttonStyle(.glassProminent)   // "similar to the borderedProminent style" — the tinted, primary-action one  [A11]
Button("Button") {}.buttonStyle(.glass(.clear))    // configurable: pass any Glass (variant / tint)  [A11]
```

Apple's guidance is to prefer these over hand-rolled `glassEffect` buttons: "Instead of creating buttons with custom Liquid Glass effects, you can adopt the look and feel of the material with minimal code by using one of the following button style APIs." [A15]

### 1.5 Bars get glass automatically — and only if you stop painting them

- "In the new design, toolbar items are placed on a Liquid Glass surface that floats above your app's content and automatically adapts to what's beneath it. Toolbar items are automatically grouped." [W3]
- "With the new design, the tab bar on iPhone floats above the content, and can be configured to minimize on scroll." [W3]
- **"Reduce your use of custom backgrounds in controls and navigation elements.** Any custom backgrounds and appearances you use in these elements might overlay or interfere with Liquid Glass or other effects that the system provides, such as the scroll edge effect. … Prefer to remove custom effects and let the system determine the background appearance." [A15]
- UIKit says the same thing more bluntly: "the bar background is now transparent by default. Remove any background customization from your navigation and toolbars. Using `UIBarAppearance` or `backgroundColor` interferes with the glass appearance." [W4]

**This is the single most important fact for our shell.** `ios/GradedTakes/UI/MainView.swift` builds its own top bar and bottom bar as `HStack`s with `.background(Brand.navy)` inside a `VStack`. Those are *not* system bars; they will never get glass, scroll-edge effects, minimise-on-scroll, or the iOS 27 restyle. Real glass chrome means moving to system `TabView` / `.toolbar`, or to Apple's documented "custom bar" path (§5.4).

### 1.6 Tab bar minimise, bottom accessory, scroll-edge effects

```swift
TabView { … }
    .tabBarMinimizeBehavior(.onScrollDown)      // iOS 26.0+; .automatic / .never / .onScrollDown / .onScrollUp; "Minimizing is supported for tab bars on only iPhone."  [A12]
    .tabViewBottomAccessory { StatusStrip() }   // iOS 26.0+; sits above the bar, collapses inline when the bar minimises  [A16]

ScrollView { … }
    .scrollEdgeEffectStyle(.hard, for: .top)    // .automatic / .soft (blurred) / .hard ("linear, nearly opaque boundary")  [A17]
```

- Scroll edge effect purpose: "Scroll views offer a `scrollEdgeEffectStyle(_:for:)` that helps maintain sufficient legibility and contrast for controls by obscuring content that scrolls beneath them. System bars like toolbars adopt this behavior by default." [A15]
- Design intent: "Scroll edge effects are not decorative! Clarify where UI and content meet. Don't use if there no floating elements." (WWDC25-356 notes [W2]); "Elements using Liquid Glass require clear separation from content to maintain legibility. Without that separation, contrast can suffer." [W2]
- iOS 27 adds the generalised `toolbarMinimizationBehavior` ("This modifier replaces `toolbarMinimizeBehavior`") and a `Tab(role: .prominent)` slot. [A24][A25]

### 1.7 Tinting glass with the brand colour (gold)

Mechanics: `.glassEffect(.regular.tint(Brand.gold))`, `.buttonStyle(.glassProminent)` + `.tint(Brand.gold)`, or UIKit `UIGlassEffect.tintColor`. Apple: "SwiftUI automatically uses a vibrant text color that adapts to maintain legibility against colorful backgrounds … the tint also uses a vibrant color that adapts to the content behind it." [W3] "Selecting a color generates a range of tones that are mapped to content brightness underneath the tinted element." [W1]

Rules (HIG "Color ▸ Liquid Glass color" [A18]):

- "By default, Liquid Glass has no inherent color, and instead takes on colors from the content directly behind it."
- "**Apply color sparingly to the Liquid Glass material, and to symbols or text on the material.** If you apply color, reserve it for elements that truly benefit from emphasis, such as status indicators or primary actions. To emphasize primary actions, apply color to the background rather than to symbols or text. … **Refrain from adding color to the background of multiple controls.**"
- "For smaller elements like toolbars and tab bars … symbols and text on these elements follow a monochromatic color scheme, becoming darker when the underlying content is light, and lighter when it's dark."
- WWDC: "Tinting should only be used to bring emphasis to primary elements and actions in the UI. Avoid tinting all your elements. When every element is tinted, nothing stands out." [W1]

This maps 1:1 onto the product's existing "ONE accent" rule: gold is allowed on **one** glass element per screen (the primary verb — e.g. the "Do now" action, or the START confirm), as a *tinted background*, and the tab bar/toolbar glyphs stay monochrome. The gold diamond mark is content on the bar, not a tint.

---

## 2. Dark glass — what Apple actually says

There is no "dark glass" API. Glass is one material that flips:

- "unlike previous materials that had a fixed light or dark appearance, each layer continuously adapts based on what's behind it. As text scrolls underneath, shadows become more prominent to create additional separation. The amount of tint and the dynamic range shift to always ensure buttons remain legible … And when needed, it can also independently switch between light and dark." [W1]
- "Small elements like navbars and tabbars, constantly adapt their appearance depending on what's behind them. They also flip from light to dark based on the background … Bigger elements, like menus or sidebars also adapt based on context, but they don't flip from light to dark. Their surface area is too big and transitions like these would be distracting." [W1]
- "When darker content scrolls under, triggering the glass itself to transition to its dark style, the effect intelligently switches to apply a subtle dimming instead, again ensuring contrast and legibility." [W1]
- UIKit: "Glass has a dark and a light appearance. It adapts to the selected `userInterfaceStyle`. … A larger size is more opaque. A smaller size is clearer, and switches between light and dark mode automatically, to increase contrast." [W4]
- "Liquid Glass appears more opaque in larger elements like sidebars to preserve legibility over complex backgrounds." [A18]

So on an obsidian ground the chrome renders in its dark style automatically — a slightly lifted, low-chroma, blurred surface with a specular rim and a shadow that deepens over text. Two design implications:

1. **Give the glass something to refract.** On a flat `#0B0B0E` ground, dark glass is nearly invisible; Apple's demos always have colour or texture under the bar ("Light from colorful content nearby can subtly spill onto its surface" [W1]). The page's roster rows, gold rules and avatars scrolling *under* the bar are what make it read as glass. That requires the web view to extend under the bars (§5.3), not sit between them as it does today.
2. **Forcing dark.** HIG Dark Mode: "Avoid offering an app-specific appearance setting" but "In rare cases, consider using only a dark appearance in the interface. For example, it can make sense for an app that supports immersive media viewing." [A19] An obsidian-only shell is defensible as a product identity (`.preferredColorScheme(.dark)` on the root), but then the pages' Daylight theme should be retired inside the app or the shell/page will disagree.

**Text on glass — the HIG rules**

- Materials: "**Help ensure legibility by using vibrant colors on top of materials.** When you use system-defined vibrant colors, you don't need to worry about colors seeming too dark, bright, saturated, or low contrast." "Thicker materials, which are more opaque, can provide better contrast for text and other elements with fine features." [A14]
- Regular vs clear: "The *regular* variant blurs and adjusts the luminosity of background content to maintain legibility of text and other foreground elements … Use the regular variant when background content might create legibility issues, or when components have a significant amount of text." "**Only use clear Liquid Glass for components that appear over visually rich backgrounds.**" Add a dimming layer under clear glass: "If the underlying content is bright, consider adding a dark dimming layer of 35% opacity." [A14] WWDC's three conditions for clear: media-rich content beneath, a dimming layer won't hurt the content, and the content on top is bold and bright. [W1] **None of the three hold for a text-dense fantasy app. Use `.regular` everywhere.**
- Contrast floors (HIG Accessibility, WCAG AA as used by Accessibility Inspector): up to 17 pt → 4.5:1; 18 pt → 3:1; bold → 3:1; "If your app supports dark mode, make sure to check the minimum contrast in both light and dark appearances." [A20] Dark Mode page: "At a minimum, make sure the contrast ratio between colors is no lower than 4.5:1. For custom foreground and background colors, strive for a contrast ratio of 7:1, especially in small text." [A19]
- Content placement: "Be aware of the placement of color in the content layer. Make sure your interface maintains sufficient contrast by avoiding overlap of similar colors in the content layer and controls … make sure its default or resting state — like the top of a screen of scrollable content — maintains clear legibility." [A18] "In steady states, such as when an app first launches, avoid intersections between content and Liquid Glass. Instead, reposition or scale the content to maintain separation." [W1]

Brand maths on obsidian (WCAG, computed for this brief):

| Pair | Ratio | Verdict |
|---|---|---|
| gold `#F2B722` on obsidian `#0B0B0E` | 10.8:1 | AAA; gold rules and gold numerals are fine at any size |
| gold on elevated `#1A1A20` | 9.5:1 | AAA |
| navy `#101B33` ink on gold fill (START chip) | 9.4:1 | AAA — keep navy/obsidian ink on gold, never white |
| light text `#EAEAF0` on obsidian | 16.4:1 | AAA |
| muted `#9A9AA6` on obsidian | 7.1:1 | meets the 7:1 "strive for" bar for small text |
| muted `#8A8A96` on elevated `#1A1A20` | 5.1:1 | AA only — the floor for 11 pt mono captions; don't go greyer |

Text *on the glass bars themselves* is not our problem to compute — use system label colours / `.foregroundStyle(.primary)` and let vibrancy do it; do not hard-code `#EAF0FA` on the bar as `Brand.navText` does today.

---

## 3. When NOT to use glass — quoted, because it decides the page design

HIG "Materials" [A14], verbatim:

> "Liquid Glass forms a distinct functional layer for controls and navigation elements — like tab bars and sidebars — that floats above the content layer, establishing a clear visual hierarchy between functional elements and content."
>
> "**Don't use Liquid Glass in the content layer.** Liquid Glass works best when it provides a clear distinction between interactive elements and content, and including it in the content layer can result in unnecessary complexity and a confusing visual hierarchy. Instead, use standard materials for elements in the content layer, such as app backgrounds. An exception to this is for controls in the content layer with a transient interactive element like sliders and toggles; in these cases, the element takes on a Liquid Glass appearance to emphasize its interactivity when a person activates it."
>
> "**Use Liquid Glass effects sparingly.** Standard components from system frameworks pick up the appearance and behavior of this material automatically. If you apply Liquid Glass effects to a custom control, do so sparingly. Liquid Glass seeks to bring attention to the underlying content, and overusing this material in multiple custom controls can provide a subpar user experience by distracting from that content. Limit these effects to the most important functional elements in your app."

WWDC25-219 [W1]:

> "You may be tempted to use Liquid Glass everywhere but it is best reserved for the navigation layer that floats above the content of your app. Consider this tableview: making it Liquid Glass would make it compete with other elements and muddy the hierarchy. So keep it in the content layer instead to ensure clarity. Similarly, always avoid glass on glass. Stacking Liquid Glass elements on top of each other can quickly make the interface feel cluttered and confusing. When placing elements on top of Liquid Glass, avoid applying the material to both layers. Instead, use fills, transparency, and vibrancy for the top elements to make them feel like a thin overlay that is part of the material."

WWDC25-284 [W4]: "Liquid Glass is designed to be an interactive layer. It floats above your content, right below your fingertips, and provides the main controls that the user touches. For that reason, limit Liquid Glass to the most important elements of your app." And on Maps: "when the sheet expands, Maps removes the buttons. This prevents glass elements from overlapping other glass elements, and keeps the illusion of a single floating layer of glass intact."

Applied to our screens:

| Screen element | Layer | Glass? |
|---|---|---|
| Top bar (wordmark, week, league switcher, share, settings) | navigation | Yes — system toolbar / glass bar |
| 5-tab bar | navigation | Yes — system `TabView` or glass bar |
| Home "Needs you" inbox groups, roster rows, status pills, opponent chips | content | **No** — standard dark surfaces |
| Verb button per inbox item ("Start him", "Claim", "Review") | control *inside* content | No glass by default; the HIG exception is only for transient activation. One floating primary verb (sticky "Do now" strip above the tab bar) may be glass — that is the `tabViewBottomAccessory` slot [A16] |
| Lineup slots, challenger line | content | No |
| Board decision cards (versus cards, compact rows) | content | No — "Consider this tableview: making it Liquid Glass would … muddy the hierarchy" |
| Ledger digest, Trade Desk grid/matrix, Sources avatars | content | No |
| Verdict chips (gold fill = START, ghost = SIT, dashed = TOSS-UP) | content | No — these are fills; on obsidian the weight encoding gets *stronger*, keep it |
| Honesty banner ("Saved copy · Sun 07 Sep 14:10", offline) | functional, transient | Could be a glass bar with the hard scroll-edge style, but a solid gold-rule strip is more honest and cheaper |

**A page full of glass cards violates the first HIG rule outright and the "glass on glass" rule as soon as the tab bar floats over them.** The obsidian *feeling* has to come from somewhere else (§8).

---

## 4. Accessibility settings — what the app must do

What the system does for native glass, automatically (WWDC25-219 [W1]):

> "Reduced Transparency makes Liquid Glass frostier and obscures more of the content behind it. Increased contrast makes elements predominantly black or white and highlights them with a contrasting border, and Reduced Motion decreases the intensity of some effects and disables any elastic properties for the material. These are available automatically whenever you use the new material. So whenever these settings are turned on at a system-level, Liquid Glass elements will get them across the board."

Apple's instruction to us: "**Test your interface with a variety of display and accessibility settings.** … people can choose a preferred look for Liquid Glass in their device's settings, or turn on accessibility settings that reduce transparency or motion in the interface. These settings can remove or modify certain effects. If you use standard components from system frameworks, this experience adapts automatically. Ensure you test your app's custom elements, colors, and animations with different configurations of these settings." [A15]

The APIs:

```swift
@Environment(\.accessibilityReduceTransparency) var reduceTransparency   // iOS 13+; "If this property's value is true, UI (mainly window) backgrounds should not be semi-transparent; they should be opaque."  [A21]
@Environment(\.colorSchemeContrast) var contrast                          // .standard / .increased  [A22]
@Environment(\.accessibilityReduceMotion) var reduceMotion

UIAccessibility.isReduceTransparencyEnabled                               // iOS 8+  [A23]
UIAccessibility.isDarkerSystemColorsEnabled                               // "whether the Increase Contrast setting is in an enabled state"  [A23]
UIAccessibility.reduceTransparencyStatusDidChangeNotification             // observe on the default center  [A23]
```

The web side is where the gap is:

| Setting | Native glass | Web page (WKWebView) |
|---|---|---|
| Reduce Transparency | automatic | **Not exposed to CSS.** WebKit has never implemented `prefers-reduced-transparency` (bug 175497 open since 2017, standards-position "Concerns"; caniuse: Safari 27/TP "Not supported"). [K5][K6] → the shell must inject it. |
| Increase Contrast | automatic | `@media (prefers-contrast: more)` maps to the iOS Increase Contrast setting (Safari 14.1 / iOS 14.5+). [K7] Also inject, for symmetry. |
| Reduce Motion | automatic | `@media (prefers-reduced-motion: reduce)` (Safari 10.1+). |
| User glass slider (26.1 Clear/Tinted; 27 slider) | automatic | Not exposed. Don't try to mirror it; keep page surfaces independent of it. |

Injection pattern (shell → page; mirrors how `data-theme` is already forwarded in `WebView.swift`):

```swift
// iOS 26 shell, alongside the existing themeScript. The values are booleans
// from UIKit, never reader input, so string interpolation is safe.
static func a11yScript() -> String {
    let rt = UIAccessibility.isReduceTransparencyEnabled
    let ic = UIAccessibility.isDarkerSystemColorsEnabled
    return """
    (function(){try{var h=document.documentElement;
    h.setAttribute('data-reduce-transparency','\(rt ? 1 : 0)');
    h.setAttribute('data-increase-contrast','\(ic ? 1 : 0)');}catch(e){}})();
    """
}
// Inject at .atDocumentStart (WKUserScript) so the first paint is right, and
// re-evaluate on UIAccessibility.reduceTransparencyStatusDidChangeNotification
// and .darkerSystemColorsStatusDidChangeNotification.
```

Page CSS contract (for the ≤2 translucent surfaces the page is allowed):

```css
/* The one floating strip that may be translucent. */
:root[data-app="ios"] .gt-float {
  background: rgba(20, 20, 24, 0.62);
  -webkit-backdrop-filter: blur(18px) saturate(140%);   /* iOS 17 readers */
  backdrop-filter: blur(18px) saturate(140%);           /* Safari 18+ unprefixed */
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);  /* the glass rim */
}

/* Fallback 1 + 2: injected by the shell (Reduce Transparency has no CSS media query). */
:root[data-reduce-transparency="1"] .gt-float,
:root[data-increase-contrast="1"] .gt-float {
  background: var(--panel);                             /* opaque token */
  -webkit-backdrop-filter: none;
  backdrop-filter: none;
  border: 1px solid var(--hairline);                    /* Increase Contrast wants a contrasting border */
}

/* Fallback 3: Increase Contrast also reaches CSS natively (Safari 14.1+). */
@media (prefers-contrast: more) {
  :root[data-app="ios"] .gt-float {
    background: var(--panel);
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
    border: 1px solid var(--hairline);
  }
}
```

When Reduce Transparency is on the shell should also make the web view opaque again (`isOpaque = true`, `backgroundColor = obsidian`) so the "window background" is opaque, exactly as the SwiftUI environment doc asks. [A21]

---

## 5. WKWebView inside a glass shell

### 5.1 Can the web view be transparent? Yes — and it already half is.

`ios/GradedTakes/Web/WebView.swift:101-103` sets `isOpaque = false` but then paints `backgroundColor = Brand.uiGround` and `scrollView.backgroundColor = Brand.uiGround` (opaque colours). For native material to show behind page content, all three must agree:

```swift
webView.isOpaque = false
webView.backgroundColor = .clear
webView.scrollView.backgroundColor = .clear
webView.underPageBackgroundColor = .clear   // overscroll area; default is "derived from the <html>/<body> background with the web view background"  [A26]
```

plus, in app mode, the page must not paint an opaque `<html>/<body>` background (`:root[data-app="ios"] { background: transparent }`).

What WebKit does with `isOpaque = false` (read from WebKit `main`, 2026-09-10 [K1]): `WKWebView._setOpaqueInternal` sends `_page->setBackgroundColor(transparentBlack)` → `WebPage::setBackgroundColor` → `LocalFrameView::updateBackgroundRecursively` → `view->setTransparent(!baseBackgroundColor.isVisible())`. So the frame view is marked transparent at the engine level, which is what §5.2 depends on. `UIView.isOpaque` doc: "You should always set the value of this property to `false` if the view is fully or partially transparent." [A27]

The same is available in the iOS 26 SwiftUI `WebView`/`WebPage` API via `.webViewContentBackground(.hidden)` — "By default, WebViews are opaque, and use the page's natural background color as their background color. Use this modifier if you would like to not use this behavior and instead provide a custom background using SwiftUI." [A28] The existing shell uses `UIViewRepresentable` + `WKWebView` deliberately (iOS 17 target, custom scheme handler); no reason to switch for this.

### 5.2 Does WebKit on iOS 26 support CSS `backdrop-filter` for page cards? Yes, twice over.

1. **Unprefixed `backdrop-filter`** shipped in Safari 18.0 (2024-09-16): "For many years, backdrop filter only worked in Safari. It was available when you prefixed the property with `-webkit-backdrop-filter`. Now, starting in Safari 18.0, you don't need the prefix." [K2] Keep the `-webkit-` line for iOS 17 readers.
2. **Backdrop-filter that samples native content behind a transparent web view** is new in Safari 26.0 / iOS 26 (WebKit blog, 2025-09-15, "WebKit API" section): "The ability to applying `backdrop-filter` to content behind a transparent webview". [K3] The engineering change (WebKit bug 286939, merged 2025-02-04): "It is desirable for `WKWebView` clients that use a transparent webview to be able to use `backdrop-filter` / `-apple-visual-effect` in order to apply effects to content behind the webview. This is currently not possible as the main frame's layer is made the backdrop root." The fix: [K4]

   ```cpp
   // Source/WebCore/rendering/RenderLayerCompositor.cpp (WebKit main, 2026-09-10)
   bool RenderLayerCompositor::backdropRootIsOpaque(const GraphicsLayer* layer) const
   {
       if (layer != rootGraphicsLayer())
           return false;
       return !viewHasTransparentBackground();
   }
   // viewHasTransparentBackground(): true when frameView->isTransparent()
   // (set by isOpaque = false, §5.1) or when the document background is not opaque.
   ```

   Before iOS 26 a page `backdrop-filter` could only blur *page* content; on iOS 26+ with a transparent web view it also blurs whatever native view sits behind the web view. There is no switch — it follows from `isOpaque = false`.

What it does **not** do: the native glass bars sit *above* the web view, so page backdrop-filters never sample the bars; and native glass samples the composited web view as ordinary pixels (glass "cannot sample other glass" is about native glass layers, a CSS blur is just content to it). So technically the stack composes. Whether it *should* is §3 and §8.

### 5.3 Scroll-edge effects and minimise-on-scroll with a web view

- Bars decide their edge appearance by observing a `UIScrollView`: "The view controller identifies a scroll view to observe by analyzing the view hierarchy … If the view hierarchy is complex, the view controller might not select the appropriate scroll view to observe. Use this method to indicate a specific scroll view." → `setContentScrollView(webView.scrollView, for: .all)` (iOS 15+). [A29] `WKWebView.scrollView` is a real `UIScrollView`, so system bars can track it.
- Custom bars over a web view: `UIScrollEdgeElementContainerInteraction` (iOS 26): "Add this interaction to a container view of views that overlay the edge of a scroll view. Any descendants of this view that should affect the shape of the edge effect, such as labels, images, glass views, and controls, will automatically do so." [A30] Evidence it works over `WKWebView.scrollView`: a developer shipped exactly that (title bar over a WKWebView) and hit a 26.1 bug only when toggling `.hard`→`.soft`; DTS replied "It's a known issue and the engineering team is investigating a fix" with a WebKit PR. [F2] (An earlier beta-4/5 regression report [F1] appears to have been fixed by release.)
- The web view must extend **under** the bars for any of this to mean anything. Today `scrollView.contentInsetAdjustmentBehavior = .never` and the web view sits between two opaque bars (`MainView.swift`). Under glass: let the bars inset the safe area, set `contentInsetAdjustmentBehavior = .automatic` (or set `obscuredContentInsets`, iOS 26, "areas of the web view that are covered by browser UI elements like tab bars or toolbars … so web content renders within the visible area" [K3][A31]), and drop the page's own `env(safe-area-inset-*)` padding in app mode so it isn't inset twice.

### 5.4 Which native chrome? Two viable shapes

**Shape A — system `TabView` (canonical, most automatic).** Five `Tab`s, each hosting a `WebView`. Gains automatic glass, light/dark flip, `tabBarMinimizeBehavior`, `tabViewBottomAccessory` for the "Do now" strip, `Tab(role: .search)` if Sources ever needs search, and whatever iOS 27 changes about the bar. Cost: five `WKWebView`s (one per tab) instead of one, which breaks the shell's current "one web view, the bar highlights what it actually shows" truth model (`MainView.swift` header comment) and multiplies memory. All five pages are the same custom-scheme origin so WebKit will normally share one web-content process, but that is an expectation, not something verified here.

**Shape B — custom glass bar over the single web view (Apple's documented "custom bar" path).** Keep one `WKWebView`. Build the bottom bar as a `GlassEffectContainer` of glass capsules and place it with `safeAreaBar(edge: .bottom)`, which "extends the edge effect of any scroll views affected by the inset safe area" [A32]; attach a `UIScrollEdgeElementContainerInteraction` to the bar's hosting view with `scrollView = webView.scrollView` for the blur boundary. Apple explicitly sanctions this: "If you use a custom bar with elements like controls, text, or icons that have content scrolling beneath them, you can register those views to use a scroll edge effect with these APIs: `safeAreaBar` / `UIScrollEdgeElementContainerInteraction`." [A15] You lose automatic minimise-on-scroll (only real tab bars minimise) unless you drive it from the web view's scroll offset yourself.

```swift
// Shape B sketch — iOS 26 only; the iOS 17–25 branch keeps today's navy bars.
@available(iOS 26, *)
struct GlassTabBar: View {
    @Binding var selected: Destination
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        GlassEffectContainer(spacing: 12) {
            HStack(spacing: 12) {
                ForEach(Destination.allCases) { d in
                    Button { selected = d } label: {
                        Label(d.title, systemImage: d.symbol)
                            .labelStyle(.iconOnly)
                            .frame(minWidth: 44, minHeight: 44)   // phone-fit rule
                    }
                    .buttonStyle(.glass)                            // monochrome glyph; NO tint on tabs
                    .accessibilityLabel(d.title)
                }
            }
        }
        .padding(.horizontal, 16)
    }
}

// Host:
WebView(…)
    .safeAreaBar(edge: .bottom) { GlassTabBar(selected: $router.destination) }
    .safeAreaBar(edge: .top)    { GlassTopBar() }   // wordmark + week + league + share + settings
```

Recommendation: **Shape B first** — it keeps the single web view and the honesty model, uses real Liquid Glass primitives (not fakes), and every rule in §3 is satisfied because the *only* glass on screen is the two bars. Re-evaluate Shape A if minimise-on-scroll or a search tab becomes a product requirement.

---

## 6. Performance — what is known

- Apple, on custom glass: "**Creating too many Liquid Glass effect containers and applying too many effects to views outside of containers can degrade performance. Limit the use of Liquid Glass effects onscreen at the same time.**" [A5] "Check for crowding or overlapping of controls … avoid overcrowding or layering Liquid Glass elements on top of each other." [A15] `backgroundExtensionEffect`: "This should often be used with only a single instance of background content with consideration of visual clarity and performance." [A33]
- Apple gates the material by GPU class on at least one platform: "Apple TV 4K (2nd generation) and newer models support Liquid Glass effects. On older devices, your app maintains its current appearance." [A15] iOS 26 itself runs on iPhone 11 (A13) and later. [T5]
- Blur mechanics (UIKit, still true under glass): a `UIVisualEffectView` with alpha < 1 "causes the system to combine the view and all the associated subviews during an offscreen render pass". [A34] CSS: "The nature of this backdrop effect forces the engine to perform more rendering passes, which will have an impact on performance. Make sure you only use this feature where it is most necessary." (WebKit, 2015, still the implementation) [K8]
- Field reports (third-party, uncontrolled): stutter and scroll jitter on iPhone 11–13 under iOS 26, with Reduce Transparency / Tinted / Reduce Motion as the recommended mitigations [T6]; a 4×2.5 h battery test on iPhone 17 Pro Max found Clear vs Tinted differ by ~1 percentage point — negligible. [T7]

Reading for our case: two native glass bars are within Apple's envelope on every supported iPhone. A scrolling list of 20–40 `backdrop-filter` cards inside a transparent web view is *N* backdrop layers, each re-sampled every frame over a live native backdrop — the exact "stacking blurs" pattern that costs on A13–A15. Cap page backdrop-filters at **two per screen** and prefer none.

---

## 7. Verdict on the architecture question

**"Native glass for chrome + transparent web view + CSS backdrop-filter glass cards" — sound on iOS 26?**

| Part | Sound? | Why |
|---|---|---|
| Native Liquid Glass for the top bar and tab bar | **Yes — this is the intended use.** | Navigation layer; automatic light/dark, Reduce Transparency, Increase Contrast, Reduce Motion, iOS 27 restyle, user slider. Requires replacing the hand-painted navy bars (§1.5). |
| Transparent `WKWebView` | **Yes.** | `isOpaque=false` + clear colours + transparent page root; engine-level transparent frame view (§5.1). Gives the bars real content to sample and lets a native obsidian ground/gradient sit behind the page. |
| CSS `backdrop-filter` in the page | **Technically yes (Safari 18 unprefixed; Safari 26 samples native content behind the web view).** | §5.2 |
| **Glass cards as the content layer** | **No.** | Violates "Don't use Liquid Glass in the content layer" [A14] and "always avoid glass on glass" [W1] the moment the tab bar floats over them; makes the material meaningless ("When every element is tinted, nothing stands out" applies to glass too); *N* live backdrops on A13–A15 [§6]; Reduce Transparency is invisible to CSS [§4]. |

**Recommended shape ("obsidian glass" without breaking the rules):**

1. **Chrome = real glass.** Two system-material bars (Shape B, §5.4), monochrome glyphs, gold only as the tinted background of the single primary verb (`.glassProminent` + `.tint(Brand.gold)`), gold diamond mark as content.
2. **Ground = native, not web.** Paint the obsidian ground natively behind the transparent web view — a near-black with a very slow vertical luminance ramp (e.g. `#0B0B0E → #14141A`) and, optionally, a faint gold vignette at the top so the top bar has warmth to refract. This is the "app background" the HIG assigns to standard materials.
3. **Content = fills, not blur.** Page cards on obsidian use the HIG dark-mode base/elevated model [A19] — opaque tiers (`#0B0B0E` ground, `#141419` panel, `#1C1C22` raised) plus a 1 px inset top highlight `rgba(255,255,255,0.06)` and a hairline `rgba(255,255,255,0.08)`. That is exactly WWDC's prescription for things layered near glass: "use fills, transparency, and vibrancy … a thin overlay". It reads as smoked glass, costs nothing, and survives every accessibility setting unchanged.
4. **At most two translucent surfaces in the page**, each functionally a floating control, not a card: the sticky "Do now" action strip on Home (or hand it to native as the bottom accessory / a glass capsule above the bar), and the lock-countdown/honesty strip if it floats. These get `backdrop-filter` with the `data-reduce-transparency` fallback (§4).
5. **Verdict encoding unchanged**: gold fill = START, ghost outline = SIT, dashed = TOSS-UP; on obsidian the weight contrast is stronger, not weaker. No green, no red — none appears in any glass API either; `.glassProminent` uses *your* tint.

**Fallback matrix**

| Condition | Chrome | Web view | Page surfaces |
|---|---|---|---|
| iOS 26/27, defaults | Liquid Glass bars | transparent, native obsidian ground behind | opaque tiers; ≤2 `backdrop-filter` floats |
| iOS 26/27 + **Reduce Transparency** | system frosts the glass automatically [W1] | set `isOpaque = true`, `backgroundColor = obsidian` (opaque window background [A21]) | inject `data-reduce-transparency=1` → floats become opaque `var(--panel)`, `backdrop-filter: none` |
| iOS 26/27 + **Increase Contrast** | system: black/white with contrasting border [W1] | unchanged | `prefers-contrast: more` + injected attribute → 1 px hairline borders on tiers, `--muted` lifted to ≥7:1 |
| iOS 26/27 + **Reduce Motion** | system disables elastic/morph [W1] | unchanged | `prefers-reduced-motion` → no morph/slide on the float |
| iOS 26.1+/27 user slider at "Tinted"/right end | system makes bars near-opaque | unchanged | unchanged — never tune the page to a slider position |
| **iOS 17–25** (deployment target) | today's navy bars (no glass API exists) | may stay opaque | same obsidian tiers; the float is a solid panel |

---

## 8. Spikes before committing (things verified in docs/source, not yet on a device here)

1. **Transparent web view + `backdrop-filter` over a native gradient** — 30 min: one `.gt-float` over a native `LinearGradient`; confirm the blur samples the native layer on the iOS 26.5 simulator and a physical A13/A15 phone; confirm overscroll shows the native ground, not white.
2. **`safeAreaBar` + `UIScrollEdgeElementContainerInteraction` over `WKWebView.scrollView`** — confirm the edge blur tracks page content, and the 26.1 `.hard`↔`.soft` bug [F2] is not hit (we will use `.soft` only).
3. **Reduce Transparency round trip** — toggle the setting with the app foregrounded; confirm the notification fires, the web view goes opaque, and the page attribute flips without reload.
4. **iOS 27 RC pass** — build once with Xcode 27 RC on the 27 RC simulator; the bar restyle (lighter dark glass, darker selected item) must not fight the gold primary verb.
5. **Frame time on iPhone 11/13** — Instruments "Animation Hitches" scrolling Home with 0 vs 2 vs 20 page backdrop-filters, to make the two-per-screen cap a number rather than a belief.

---

## 9. What this brief did not settle

- Exact `GlassEffectContainer.spacing` and capsule sizes for the tab bar — needs the design canvas.
- Whether the honesty banner belongs in native chrome (glass, hard edge) or stays a page element. Both satisfy the honesty contract; native is cheaper to keep truthful because `PageService.served` already lives there.
- Shape A (five web views) memory footprint — unmeasured.

---

## 10. Sources

Apple documentation (fetched 2026-09-10 via the developer.apple.com doc JSON):

- [A1] `glassEffect(_:in:)` — https://developer.apple.com/documentation/swiftui/view/glasseffect(_:in:)
- [A2] `Glass` — https://developer.apple.com/documentation/swiftui/glass
- [A3] `Glass.tint(_:)` — https://developer.apple.com/documentation/swiftui/glass/tint(_:)
- [A4] `Glass.interactive(_:)` — https://developer.apple.com/documentation/swiftui/glass/interactive(_:)
- [A5] Applying Liquid Glass to custom views — https://developer.apple.com/documentation/swiftui/applying-liquid-glass-to-custom-views
- [A6] `Glass.clear` — https://developer.apple.com/documentation/swiftui/glass/clear
- [A7] `GlassEffectContainer` — https://developer.apple.com/documentation/swiftui/glasseffectcontainer
- [A8] `glassEffectID(_:in:)` — https://developer.apple.com/documentation/swiftui/view/glasseffectid(_:in:)
- [A9] `glassEffectUnion(id:namespace:)` — https://developer.apple.com/documentation/swiftui/view/glasseffectunion(id:namespace:)
- [A10] `GlassEffectTransition` — https://developer.apple.com/documentation/swiftui/glasseffecttransition
- [A11] `PrimitiveButtonStyle.glass`, `.glassProminent`, `.glass(_:)` — https://developer.apple.com/documentation/swiftui/primitivebuttonstyle/glass , …/glassprominent , …/glass(_:)
- [A12] `tabBarMinimizeBehavior(_:)` / `TabBarMinimizeBehavior` — https://developer.apple.com/documentation/swiftui/view/tabbarminimizebehavior(_:) , https://developer.apple.com/documentation/swiftui/tabbarminimizebehavior
- [A13] `UIDesignRequiresCompatibility` — https://developer.apple.com/documentation/bundleresources/information-property-list/uidesignrequirescompatibility
- [A14] HIG ▸ Materials (updated 2025-09-09) — https://developer.apple.com/design/human-interface-guidelines/materials
- [A15] Technology Overviews ▸ Adopting Liquid Glass — https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass
- [A16] `tabViewBottomAccessory(content:)` — https://developer.apple.com/documentation/swiftui/view/tabviewbottomaccessory(content:)
- [A17] `ScrollEdgeEffectStyle` / `scrollEdgeEffectStyle(_:for:)` — https://developer.apple.com/documentation/swiftui/scrolledgeeffectstyle , https://developer.apple.com/documentation/swiftui/view/scrolledgeeffectstyle(_:for:)
- [A18] HIG ▸ Color ▸ Liquid Glass color — https://developer.apple.com/design/human-interface-guidelines/color
- [A19] HIG ▸ Dark Mode — https://developer.apple.com/design/human-interface-guidelines/dark-mode
- [A20] HIG ▸ Accessibility (contrast table) — https://developer.apple.com/design/human-interface-guidelines/accessibility
- [A21] `EnvironmentValues.accessibilityReduceTransparency` — https://developer.apple.com/documentation/swiftui/environmentvalues/accessibilityreducetransparency
- [A22] `EnvironmentValues.colorSchemeContrast` — https://developer.apple.com/documentation/swiftui/environmentvalues/colorschemecontrast
- [A23] `UIAccessibility.isReduceTransparencyEnabled`, `.isDarkerSystemColorsEnabled`, `.reduceTransparencyStatusDidChangeNotification` — https://developer.apple.com/documentation/uikit/uiaccessibility/isreducetransparencyenabled , …/isdarkersystemcolorsenabled , …/reducetransparencystatusdidchangenotification
- [A24] Xcode 27 RC Release Notes; iOS & iPadOS 27 RC Release Notes ("You can use `toolbarMinimizationBehavior` to control bar minimization behavior. This modifier replaces `toolbarMinimizeBehavior`.") — https://developer.apple.com/documentation/xcode-release-notes/xcode-27-release-notes , https://developer.apple.com/documentation/ios-ipados-release-notes/ios-ipados-27-release-notes
- [A25] SwiftUI updates (June 2026 / June 2025 sections) — https://developer.apple.com/documentation/updates/swiftui
- [A26] `WKWebView.underPageBackgroundColor` — https://developer.apple.com/documentation/webkit/wkwebview/underpagebackgroundcolor
- [A27] `UIView.isOpaque` — https://developer.apple.com/documentation/uikit/uiview/isopaque
- [A28] `webViewContentBackground(_:)` — https://developer.apple.com/documentation/swiftui/view/webviewcontentbackground(_:)
- [A29] `UIViewController.setContentScrollView(_:for:)` — https://developer.apple.com/documentation/uikit/uiviewcontroller/setcontentscrollview(_:for:)
- [A30] `UIScrollEdgeElementContainerInteraction` — https://developer.apple.com/documentation/uikit/uiscrolledgeelementcontainerinteraction
- [A31] `WKWebView.obscuredContentInsets` — https://developer.apple.com/documentation/webkit/wkwebview/obscuredcontentinsets
- [A32] `safeAreaBar(edge:alignment:spacing:content:)` — https://developer.apple.com/documentation/swiftui/view/safeareabar(edge:alignment:spacing:content:)
- [A33] `backgroundExtensionEffect()` — https://developer.apple.com/documentation/swiftui/view/backgroundextensioneffect()
- [A34] `UIVisualEffectView` — https://developer.apple.com/documentation/uikit/uivisualeffectview

WWDC25 sessions (quotes are from Apple's on-page transcripts):

- [W1] 219 "Meet Liquid Glass" — https://developer.apple.com/videos/play/wwdc2025/219/
- [W2] 356 "Get to know the new design system" — https://developer.apple.com/videos/play/wwdc2025/356/ (plus WWDCNotes summary https://wwdcnotes.com/documentation/wwdc25-356-get-to-know-the-new-design-system/)
- [W3] 323 "Build a SwiftUI app with the new design" — https://developer.apple.com/videos/play/wwdc2025/323/
- [W4] 284 "Build a UIKit app with the new design" — https://developer.apple.com/videos/play/wwdc2025/284/

WebKit:

- [K1] WebKit source, `main` on 2026-09-10: `Source/WebKit/UIProcess/API/ios/WKWebViewIOS.mm` (`_setOpaqueInternal`), `Source/WebKit/WebProcess/WebPage/WebPage.cpp` (`setBackgroundColor`), `Source/WebCore/page/LocalFrameView.cpp` (`updateBackgroundRecursively`), `Source/WebCore/rendering/RenderLayerCompositor.cpp` (`viewHasTransparentBackground`, `backdropRootIsOpaque`) — https://github.com/WebKit/WebKit
- [K2] WebKit Features in Safari 18.0 (2024-09-16) — https://webkit.org/blog/15865/webkit-features-in-safari-18-0/
- [K3] WebKit Features in Safari 26.0 (2025-09-15), "WebKit API" — https://webkit.org/blog/17333/webkit-features-in-safari-26-0/
- [K4] Bug 286939 "Allow backdrop blending outside of transparent webviews" (merged 2025-02-04) — https://bugs.webkit.org/show_bug.cgi?id=286939 ; commit https://github.com/WebKit/WebKit/commit/6a3a1914b4c927b42e0071e2b7dd645acd6340f5
- [K5] Bug 175497 `prefers-reduced-transparency` (status NEW) — https://bugs.webkit.org/show_bug.cgi?id=175497
- [K6] caniuse `prefers-reduced-transparency` (Safari 27/TP: not supported) — https://caniuse.com/wf-prefers-reduced-transparency
- [K7] `prefers-contrast` support (Safari 14.1 / iOS 14.5) — https://web-platform-dx.github.io/web-features-explorer/features/prefers-contrast/
- [K8] Introducing Backdrop Filters (2015-08-10) — https://webkit.org/blog/3632/introducing-backdrop-filters/

Apple Developer Forums:

- [F1] "Should UIScrollEdgeElementContainerInteraction work with a WKWebView's scroll view?" (beta 4/5 regression, FB19386650) — https://developer.apple.com/forums/thread/795816
- [F2] "UIScrollEdgeElementContainerInteraction uses wrong mix-in color over WKWebView on iOS 26.1" (DTS: known issue, WebKit PR 52365) — https://developer.apple.com/forums/thread/803917

Third-party (dated; used only for release timing, the user-facing settings, and field performance reports):

- [T1] 9to5Mac, 2026-09-09, "Apple confirms iOS 27 release date: September 14" — https://9to5mac.com/2026/09/09/apple-confirms-ios-27-release-date-september-14/
- [T2] MacRumors, 2026-07-30, "iOS 27: Tone Down Liquid Glass Transparency" — https://www.macrumors.com/how-to/ios-27-tone-down-liquid-glass-transparency/ ; 9to5Mac, 2026-08-11 — https://9to5mac.com/2026/08/11/ios-27-beta-5-lets-you-make-liquid-glass-more-transparent-than-ever/
- [T3] MacRumors, 2025-11-03, "Apple Releases iOS 26.1 With Liquid Glass Toggle…" — https://www.macrumors.com/2025/11/03/apple-releases-ios-26-1/
- [T4] designfornative.com, 2026-06-10, "What Designers Need to Know About iOS 27" (beta-1 observations, no Apple citation) — https://designfornative.com/what-designers-need-to-know-about-ios-27/
- [T5] MacRumors, 2025-06-09, "iOS 26 is Compatible With the iPhone 11 and Newer" — https://www.macrumors.com/2025/06/09/ios-26-supports-iphone-11-and-newer/
- [T6] BGR, 2025-12-15, "Is iOS 26 Slow On Your Older iPhone?" — https://www.bgr.com/2047698/how-to-fix-ios-26-slowing-down-iphone-guide/
- [T7] MacRumors, 2025-10-24, "iOS 26.1 Beta Liquid Glass Battery Drain Test" — https://www.macrumors.com/2025/10/24/ios-26-1-liquid-glass-battery-test/
