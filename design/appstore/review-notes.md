# App Review "Notes for Review" — paste-ready draft

Supporting file for `docs/APPSTORE.md`. Drafted 9 September 2026.

Guideline 2.3.1(a) says: *"All new features, functionality, and product changes must be described
with specificity in the Notes for Review section of App Store Connect (generic descriptions will be
rejected)."* This file exists so that sentence is never the reason for a rejection.

Fill the `<>` placeholders. Keep it under ~2,000 characters if possible; reviewers skim.

---

## Notes for Review

**What this app does.** War Room is a fantasy-football decision tool. It does not host leagues, take
wagers, hold currency, or run contests. It reads a user's own league (roster, matchup, scoring
settings) and computes start/sit and trade guidance from that league's own configuration.

**The computation is ours, not aggregation.** The app calculates value-based-drafting replacement
baselines from the league's roster requirements and projection pool, runs a survival model over ADP
to estimate player availability, assigns positional tiers, and maintains a public accuracy ledger
that grades every prediction source — including our own — against what actually happened. The
ledger is unique to this app; no competing fantasy app publishes one.

**Native functionality (please exercise these).**
- Push notifications via APNs at the Time Sensitive interruption level. The core alert is
  "your starter has been ruled out" delivered before kickoff; it must break through Focus. To see
  it fire on demand: <exact steps, e.g. Settings > Developer > Send test alert>.
- Offline: the app ships its rendered pages on device. Enable Airplane Mode and every page still
  opens and renders in full.
- Home Screen and Lock Screen widgets (WidgetKit) showing the week's undecided verdicts.
- Native tab navigation, native sheet presentation, native pull-to-refresh, haptics on verdict change.
- Share sheet: share a verdict card to a league group chat.
- Siri / Shortcuts via App Intents: "<example phrase>".
- Face ID / Touch ID app lock (league mates are competitors; the trade desk is sensitive).
- Background refresh pre-warms Sunday's pages before kickoff.

A 30-second screen recording of the Time Sensitive alert firing and the widget updating from it is
attached to this submission.

**Third-party data (guideline 5.2.2).**
- **Sleeper** — read-only public API. Written permission from Sleeper for our use is attached to
  this submission.
- **Yahoo Fantasy Sports** — official API, OAuth 2.0, application approved on <date>; our client ID
  is <id>. Confirmation attached. The required attribution "Fantasy data provided by Yahoo Fantasy",
  linking to Yahoo Fantasy, appears on <screen name> in the app.
- **ESPN** — the app does **not** read ESPN. It does not request, store, or transmit ESPN
  credentials or cookies, and makes no automated request to any ESPN endpoint. Users with an ESPN
  league may type or paste their own roster manually; that data is user-entered only. We state this
  proactively because "ESPN" appears in our league-type picker.

**Demo account.** Username <...>, password <...>. This account is seeded with a complete league so
every page renders in full.

**One deliberate behaviour worth flagging.** This app is designed to say what it does not know. When
a data source is unavailable or a sample is too small to be meaningful, the affected section prints
a "no data" state and asserts nothing, rather than showing a confident number it cannot support.
This is intentional product behaviour, not an incomplete build. The demo account above is seeded so
you should not encounter it; if you do, <page name> demonstrates the fully-populated state.

**Age rating.** Rated 13+ for Frequent Contests. The app contains no gambling and no simulated
gambling: no wagering mechanic, no real or virtual currency, no odds, lines, spreads, or
sportsbook links.

**Export compliance.** HTTPS via URLSession/WKWebView only — encryption built into the operating
system. No proprietary cryptography. `ITSAppUsesNonExemptEncryption` is set to `false`.

---

## Attachments checklist

- [ ] Sleeper written permission (email from an authorised Sleeper contact)
- [ ] Yahoo Fantasy Sports API access confirmation + client ID
- [ ] 30-second demo video: Time Sensitive push firing, then the widget updating from it
- [ ] Demo account credentials, tested from a signed-out device the morning of submission

## Pre-submission smoke test (run in this order, on a real device)

1. Sign out entirely. Install the build fresh from TestFlight.
2. Sign in with the **reviewer demo account**. Confirm every tab renders fully — no "no data" states.
3. Airplane Mode on. Reopen every tab. Confirm all render from the on-device bundle.
4. Airplane Mode off. Trigger the test alert. Confirm it arrives with a Focus mode active.
5. Add the widget to the Home Screen and the Lock Screen. Confirm both populate.
6. Run the Siri phrase. Confirm it resolves.
7. Share a verdict card. Confirm the share sheet opens and the image is correct.
8. Confirm the Yahoo attribution string is visible and its link opens Yahoo Fantasy.
9. Confirm the privacy policy link inside the app opens and loads.
10. Confirm the app icon on the Home Screen is the 1024px opaque artwork, not a placeholder.
