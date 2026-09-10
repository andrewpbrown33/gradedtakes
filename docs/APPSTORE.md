# The App Store path

**GO/NO-GO, 9 September 2026: NO-GO for the weekend. There is no path — none, at any price — that puts a native iPhone app from this project on the App Store by Sunday 13 September 2026. Four days from today, with enrolment not yet started, no server, no APNs key, no binary and no metadata. Use the PWA this weekend. The realistic App Store date is mid-December 2026, and January 2027 is the pessimistic case.**

*Researched and written 9 September 2026 (a Wednesday; week-1 Sunday is four days out). Every claim below carries a URL and an access date — see [Evidence](#evidence). This document owns no engine code and changed none.*

---

## Contents

1. [Why the weekend is impossible](#1-why-the-weekend-is-impossible)
2. [Enrolment](#2-enrolment)
3. [Review](#3-review)
4. [The guideline 4.2 problem](#4-the-guideline-42-problem)
5. [Guideline 5.2.2 and third-party data](#5-guideline-522-and-third-party-data)
6. [Gambling, contests, and the age rating](#6-gambling-contests-and-the-age-rating)
7. [The build choice](#7-the-build-choice)
8. [Push notifications](#8-push-notifications)
9. [App Store Connect checklist](#9-app-store-connect-checklist)
10. [Week-by-week timeline](#10-week-by-week-timeline)
11. [Top five rejection risks](#11-top-five-rejection-risks)
12. [Evidence](#evidence)

---

## 1. Why the weekend is impossible

Not one of these is a guess. Each is a hard gate with a citation later in this document.

| Gate | Minimum realistic time | Can it clear by Sun 13 Sep? |
|---|---|---|
| Apple Developer Program enrolment (individual) | 24–48h claimed; weeks observed in 2026 | **Maybe.** Not reliably. |
| Apple Developer Program enrolment (organisation) | D-U-N-S: up to 5 business days from D&B + up to 2 business days for Apple to receive it, *then* Apple verification | **No.** Cannot even reach the point of buying the membership. |
| A server that runs the Python renderers and holds device tokens | 2–3 weeks | **No.** Does not exist. |
| A submittable binary with enough native surface to survive 4.2 | 4–8 weeks | **No.** |
| App Review, first submission, brand-new account | Apple publishes 90% under 24h *on average across all submissions*; a first binary from a new account is the slow tail | **No.** Nothing to submit. |
| Xcode 26 + iOS 26 SDK (mandatory for all uploads since 28 April 2026) | Toolchain install | Yes, but irrelevant on its own. |

**The one thing worth doing this week on the native track** is not code. It is the two longest-lead items with no published SLA, both of which gate the binary and neither of which is blocked by anything else: send the Sleeper licensing email and file the Yahoo Fantasy Sports API access application. See [§5](#5-guideline-522-and-third-party-data). Start them today; they may take longer than the build.

**The honest reframe.** If the goal is "an app my league uses this season," the App Store cannot deliver it — its earliest credible arrival is the fantasy playoffs. Two channels can deliver this season:

- **The PWA**, this weekend, via the other agent's work. Real push on iOS 16.4+, real home-screen icon, zero Apple gatekeeping.
- **TestFlight**, in roughly five to six weeks, as the *actual distribution channel for this season*. External TestFlight holds up to 10,000 testers and needs only Beta App Review of the first build per version — not full App Review. For an 8-team and a 10-team league, TestFlight is not a staging step; it is the product channel. Caveat: builds expire after 90 days, so a season needs two or three uploads.

Treat the App Store as a 2027-season product with a December TestFlight, and stop treating it as this season's channel.

---

## 2. Enrolment

### Cost

> "The Apple Developer Program is 99 USD per membership year. Prices may vary by region and are listed in local currency during the enrollment process."
> — [Apple, *Become a member*](https://developer.apple.com/programs/enroll/), accessed 9 Sep 2026

A free Apple Account gets you Xcode, beta OSes, on-device testing with a personal team, and the forums. It does **not** get you App Store distribution, TestFlight, App Store Connect, or push notifications — all four require the paid membership ([Apple, *Developer account overview*](https://developer.apple.com/support/compare-memberships/)). A free personal team caps at 10 App IDs and 3 devices, and its provisioning profiles **expire 7 days from issuance** — the app on the phone simply stops launching until you rebuild from Xcode. That is a demo mechanism, not a distribution mechanism.

### Individual / sole proprietor

> "If you're an individual or sole proprietor/single person business, you'll need an Apple Account with two-factor authentication turned on and be the legal age of majority in your region. Make sure to use your legal name in the first and last name fields of your Apple Account. Using an alias, nickname, or company name as your first or last name will cause a delay in the approval of your enrollment."
> — [Apple, *Become a member*](https://developer.apple.com/programs/enroll/)

Apple also confirms email, phone, and address; **P.O. boxes are not accepted**. Individuals can enrol through the Apple Developer app on iPhone, iPad or Mac in supported regions ([Apple, *Enrolling, verifying, and renewing with the Apple Developer app*](https://developer.apple.com/help/account/membership/enrolling-in-the-app/)). Your App Store seller name will be your **personal legal name** — worth knowing before you publish under it.

### Organisation — and why D-U-N-S is the wall

An organisation needs, per Apple's [Enrollment help page](https://developer.apple.com/help/account/membership/program-enrollment/) and the [enrol page](https://developer.apple.com/programs/enroll/):

1. **Legal entity status.** > "Your organization must be a legal entity that can enter into contracts with Apple. We do not accept DBAs, fictitious business names, trade names, or branches."
2. **A D-U-N-S Number.** > "Your organization (excluding government entities) must have a D-U-N-S Number so that we can verify your organization's identity, legal entity status, and address."
3. **Legal binding authority** — the Account Holder must be able to bind the entity.
4. **A work email on the organisation's own domain.**
5. **A public, functional website on that domain.** > "Links to social media webpages or websites that contain minimal content or display a message from a domain registrar won't be accepted."

Organisations enrol only through the web, and — critically — > "must wait for Apple Developer Support verification before purchasing membership."

The D-U-N-S clock, in Apple's own words ([D-U-N-S Number help](https://developer.apple.com/help/account/membership/D-U-N-S/)):

> "After requesting a D‑U‑N‑S Number, please allow up to 5 business days to receive your number from D&B. Expediting your D‑U‑N‑S Number creation process will not shorten this waiting period."
> "Once you receive your D‑U‑N‑S Number, please allow up to 2 business days for Apple to receive your information from D&B."
> "If your application has taken longer than two weeks to process, please email D&B."

Apple also warns organisations > "may be asked for business documents that are notarized."

### Realistic elapsed time

Apple publishes **no** end-to-end enrolment SLA. The only time commitment on any Apple page is about the *purchase* step:

> "If you haven't received a membership confirmation within 24 hours of your purchase, contact us."
> — [Apple, *Enrollment* help](https://developer.apple.com/help/account/membership/program-enrollment/)

That is not the identity check. Reality in 2026, from Apple's own developer forums: threads titled ["Apple Developer Program Enrollment Pending for Over 3 Weeks (Identity Verification)"](https://developer.apple.com/forums/thread/817247) and ["Apple Developer Program Enrollment Stuck for 3+ Weeks — No Response from Support"](https://developer.apple.com/forums/thread/821717). The two most common stalls are a first/last name on the Apple Account that isn't the legal name, and paying with someone else's card — both trigger a manual government-photo-ID review.

**Plan on:**

| Path | Best case | Plan for | Worst observed |
|---|---|---|---|
| Individual | 24–48 hours | **1 week** | 3+ weeks |
| Organisation | ~2 weeks | **4 weeks** | 6+ weeks |

**Can it complete before 13 September 2026?** Individual: possibly, if you start today and nothing snags — but that gets you a *membership*, not an app. Organisation: **no**, categorically; the D-U-N-S step alone consumes more business days than remain. Either way the answer to "an app on the App Store this weekend" is unchanged: no.

**Recommendation: enrol as an individual, today.** It is $99, it is the fast path, and it unblocks the APNs key and TestFlight — the two things the native track actually needs first. Converting an individual account to an organisation later is a supported Apple process; waiting for a D-U-N-S number that gates nothing you can build this month is not.

---

## 3. Review

### What Apple publishes

> "On average, 90% of submissions are reviewed in less than 24 hours."
> — [Apple, *App Review*](https://developer.apple.com/distribute/app-review/), accessed 9 Sep 2026

Read that statistic honestly. It is an average over *all* submissions, and the overwhelming majority of submissions are minor updates from established accounts with an unchanged review surface. It is not a prediction for your first binary.

### What a first submission from a brand-new account actually experiences

There is no Apple-published figure for this cohort. What is structurally true:

- The **first binary triggers a full metadata review**, not just a binary review: name, subtitle, keywords, description, screenshots, category, age rating, privacy policy, App Privacy label, export compliance and review notes are all first-time inputs, and any one of them can bounce the submission.
- Third-party trackers in 2026 report more variance than the 90% figure suggests, with "Waiting for Review" sometimes running three to seven days in busy periods and new apps taking longer than updates ([AppCompliance, *How Long Does App Store Review Take in 2026*](https://appcompliance.io/blog/app-store-review-time-2026/)). Submission volume is reported up roughly 24% on the back of AI-generated apps, and Mac App Store review times have visibly lengthened ([Michael Tsai, Mar 2026](https://mjtsai.com/blog/2026/03/02/mac-app-store-review-times-increasing/)).
- Apps that touch a sensitive category get extra scrutiny. Apple says so explicitly about gambling: > "Only include this functionality if you've fully vetted your legal obligations everywhere you make your app available and are prepared for extra time during the review process." (Guideline 5.3.) This app should not trip 5.3 (see [§6](#6-gambling-contests-and-the-age-rating)) but it sits adjacent to it, and reviewers benchmark against category peers.

### The rejection loop cost

A rejection is not a queue position; it is a restart. App Store Connect moves the submission into Unresolved Issues, you fix, you resubmit, and you re-enter the queue.

The cost is not uniform, and this matters for planning:

| Rejection type | Fix time | Round-trip cost |
|---|---|---|
| Metadata (2.3.x), missing privacy URL, wrong screenshot size | hours | 1–3 days |
| Missing/broken demo account (2.1) | hours | 1–3 days |
| Age rating mismatch | hours | 1–3 days |
| **5.2.2** — no authorisation for a third-party service | days to *never* | 1 week, or the feature dies |
| **4.2** — minimum functionality | **days to weeks of engineering** | 2–6 weeks |

A 4.2 rejection is the expensive one because the remedy is not a resubmission, it is a product change. Budget **two rejection rounds** before first approval and you will usually be right; budget zero and the schedule is fiction. There is an appeal path (the App Review Board), but appealing a 4.2 with an unchanged binary is the slowest possible way to lose.

---

## 4. The guideline 4.2 problem

### The text, verbatim

> **4.2 Minimum Functionality**
>
> Your app should include features, content, and UI that elevate it beyond a repackaged website. If your app is not particularly useful, unique, or "app-like," it doesn't belong on the App Store. If your App doesn't provide some sort of lasting entertainment value or adequate utility, it may not be accepted. Apps that are simply a song or movie should be submitted to the iTunes Store. Apps that are simply a book or game guide should be submitted to the Apple Books Store.
>
> **4.2.1** Apps using ARKit should provide rich and integrated augmented reality experiences; merely dropping a model into an AR view or replaying animation is not enough.
>
> **4.2.2** Other than catalogs, apps shouldn't primarily be marketing materials, advertisements, web clippings, content aggregators, or a collection of links.
>
> **4.2.3 (i)** Your app should work on its own without requiring installation of another app to function.
> **4.2.3 (ii)** If your app needs to download additional resources in order to function on initial launch, disclose the size of the download and prompt users before doing so.

— [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), accessed 9 Sep 2026

Two phrases in there are aimed squarely at this project and should be read as threats, not background:

- **"repackaged website."** The pages are already excellent responsive HTML. That is the asset *and* the accusation.
- **"content aggregators."** This app reads seventeen weighted sources. A reviewer skimming the sources page could reasonably file it under 4.2.2 unless the computed layer is unmissable in the first ten seconds.

And **4.2.3(i)** — "should work on its own without requiring installation of another app" — is the guideline that quietly kills the ESPN cookie flow, which requires the user to go to Safari, be logged in to ESPN, and extract two cookies. That is exactly the shape 4.2.3(i) prohibits.

### Two adjacent rules that got worse on 8 June 2026

Apple revised the guidelines on **8 June 2026** ([Apple Developer News](https://developer.apple.com/news/?id=a233fmpw)); among the changes, "4.3(b): clarifies the basis for the guideline and adds examples." The new 4.3(b) reads:

> "Don't submit apps that are indistinguishable from what's already widely available. Opportunistically creating variants of existing app categories or popular apps degrades App Store discovery, reduces overall app quality, and harms both users and developers. Certain kinds of apps … are well established on the App Store and we will not accept new submissions unless they offer a **meaningfully different or improved experience**. We may remove these apps from the App Store going forward if they are not updated, improved, or do not attract customers."

Fantasy football tools are a crowded category with ESPN, Yahoo and Sleeper on the shelf. The differentiator that answers 4.3(b) is not the UI — it is **the accuracy ledger**: a public, graded scorecard of every source's past calls. No competitor ships one. Lead with it, in the description, in the screenshots, and in the review notes.

And **4.2.6**:

> "Apps created from a commercialized template or app generation service will be rejected unless they are submitted directly by the provider of the app's content."

This is survivable — you *are* the content provider — but only if the app ships from **your own** developer account. If a "turn your site into an app" vendor submits on your behalf, 4.2.6 rejects it outright. Do not let a vendor own the account.

### What actually makes a wrapper pass

Apple publishes no checklist, and anyone who hands you one is selling something. The operative test is whether a reviewer, holding the phone for ninety seconds, believes this could not have been a website. The practitioner consensus is consistent: the apps that pass are the ones where a webview is *surrounded* by native code — native navigation, APNs push, real offline handling, and OS integration ([MobiLoud](https://www.mobiloud.com/blog/app-store-review-guidelines-webview-wrapper), [Median.co](https://median.co/blog/will-apple-approve-my-webview-app), both accessed 9 Sep 2026).

### The concrete list for *this* app

Ordered by 4.2 value per developer-week. This project has an unusual advantage: its pages are already self-contained static HTML with fonts and avatars embedded as `data:` URIs and **zero network fetches at open**. Offline — normally the expensive one — is nearly free here.

**Tier 1 — do not submit without these.**

1. **Native push via APNs, at `timeSensitive` interruption level.** The "your starter was just ruled out" alert. This is simultaneously the product's killer feature and the strongest single 4.2 argument, because it is categorically unavailable to a website. See [§8](#8-push-notifications).
2. **Genuine offline.** Ship the rendered bundle on-device (all eleven current pages total **3.3 MB** — measured today, small enough to embed or cache outright) and serve from the local bundle first, refreshing in the background. The app then works in a stadium with no bars. This is a demonstrable, reviewer-testable capability a website cannot claim, and the architecture already hands it to you.
3. **Native chrome around the webview.** A SwiftUI `TabView` for Home / Lineup / Board / Trade Desk / Sources; native pull-to-refresh; native bottom sheets. The design system's `sheet` + `sheets_script` components map directly onto `UISheetPresentationController` detents — the interaction model is already the native one, it just needs the native implementation. Haptics on a verdict change.
4. **WidgetKit widget.** "Sunday, 11:40am — three verdicts in doubt," in the gold accent, on the home screen and the lock screen. Widgets are, to a reviewer, unambiguous proof of native work.
5. **Share sheet.** `UIActivityViewController` to push a rendered verdict card into the league group chat. This is also the growth loop.

**Tier 2 — cheap, and each one removes a reviewer objection.**

6. **App Intents / Siri + Shortcuts.** "Hey Siri, who do I start at flex?" and a Shortcuts action so the owner can automate his own Sunday.
7. **Background refresh** (`BGAppRefreshTask`) to pre-warm the Sunday bundle before kickoff, so the push taps into an already-loaded page.
8. **Face ID / Touch ID app lock.** Not a checkbox — a real product requirement. Your league mates are your competitors, and the trade desk names who you think is exploitable.
9. **Universal Links / deep links** from the digest email straight to a player row.
10. **Spotlight indexing** (`CSSearchableIndex`) of players, so a home-screen search deep-links into the board.

**Tier 3 — high value, high cost, and one has a new rule attached.**

11. **Live Activity** (ActivityKit) for Sunday: your score vs your opponent's, live on the lock screen. Note that the 8 June 2026 revision added **4.5.3**, clarifying "that Live Activities may not be used to spam, phish, or send unsolicited messages to customers." Use it for the live matchup only.
12. **Notification actions and a Notification Content Extension** — "Bench him" / "Show me the swap" straight from the banner, with the verdict chip rendered in the expanded notification.
13. **Apple Watch complication.** Genuinely compelling for this product and genuinely expensive. Not for v1.

**Then write the review notes to match.** Guideline 2.3.1(a): "All new features, functionality, and product changes must be described with specificity in the Notes for Review section of App Store Connect (**generic descriptions will be rejected**)." Name the computation — VBD replacement baselines, the survival model, tier assignment, the graded accuracy ledger — as *your own work*, not aggregation. Attach a 30-second screen recording showing the Time Sensitive alert firing and the widget updating from it. That video is the cheapest 4.2 insurance available.

---

## 5. Guideline 5.2.2 and third-party data

### The text, verbatim

> **5.2.2 Third-Party Sites/Services:** If your app uses, accesses, monetizes access to, or displays content from a third-party service, ensure that you are specifically permitted to do so under the service's terms of use. **Authorization must be provided upon request.**

— [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), accessed 9 Sep 2026

Four words carry the weight: *authorization must be provided upon request*. Not "must exist." Not "must be plausible." **Provided.** On request. As a document, attached in App Store Connect. And Apple's forums are consistent about what a 5.2.2 rejection asks for: attach documentary evidence in the App Review Information section evidencing that you have all necessary rights or permissions ([developer.apple.com/forums/thread/134224](https://developer.apple.com/forums/thread/134224), [thread/105345](https://developer.apple.com/forums/thread/105345)). Submitting falsified documentation is grounds for terminating the developer account.

### Source-by-source assessment

**Sleeper — one email away from clean.**

Sleeper's own documentation says:

> "The Sleeper API is a read-only HTTP API that is free to use for non-commercial purposes."
> "For commercial use of the Sleeper API, please reach out to us directly to discuss licensing."
> "No API Token is necessary, as you cannot modify contents via this API."
> "Be mindful of the frequency of calls. A general rule is to stay under 1000 API calls per minute, otherwise, you risk being IP-blocked."
> — [docs.sleeper.com](https://docs.sleeper.com/), accessed 9 Sep 2026

A free App Store app is still a distributed product, and "non-commercial" is a term Apple's reviewer will not adjudicate for you. The vendor *invites* the conversation. **Send the email this week**, get a one-paragraph written permission, and attach it to App Review Information. This is the single cheapest de-risking action on the whole list.

**Yahoo — an application, with an unknown clock.**

Yahoo runs an official, sanctioned API with OAuth 2.0 and a gated application form. The [access application](https://sports.yahoo.com/developer/access/) asks for a clear product description, the specific Yahoo Fantasy Sports data required, the intended user base ("including where access is limited to personal or single league use"), and a projected user count for the first 3–6 months. Yahoo states: "Each application is reviewed by the Yahoo Fantasy Sports team," and warns that "incomplete or insufficiently detailed submissions cannot be evaluated and will be closed without further correspondence." Access is **read-only by default**.

Two deliverables follow from this that touch the app itself, not just paperwork:

- **Attribution is a UI requirement.** Developers must include "Fantasy data provided by Yahoo Fantasy" within the product, linking back to Yahoo. That string has to appear in the app, in the design system's voice, before submission — not bolted on after a rejection.
- **Get two answers in writing before you build on it:** may you monetise, and how Yahoo's data-retention rules interact with an accuracy ledger that by definition stores past calls.

No published approval SLA. Treat it as an unknown-length gate and start it now.

**ESPN — the answer is no, and it is not close.**

Can a native binary ship with an ESPN feature? **No.** ESPN has offered no sanctioned public API for fantasy since 2014; the local build works by using the user's own browser cookies (`espn_s2` / `SWID`), which the community reverse-engineered ([cwendt94/espn-api](https://github.com/cwendt94/espn-api), accessed 9 Sep 2026). Five independent rules each kill it on their own:

1. **5.2.2.** There is no authorisation to produce. When App Review asks — and for a feature reading a competitor platform's *private league* data, they will — the truthful answer is "none." That is a rejection plus a bad-faith mark on a brand-new account.
2. **2.1(a) App Completeness.** > "include demo account info (and turn on your back-end service!) if your app includes a login." You cannot hand Apple a live ESPN session cookie for a demo, and you cannot ask a reviewer to extract their own.
3. **4.2.3(i).** > "Your app should work on its own without requiring installation of another app to function." A flow that requires Safari and a logged-in ESPN session is the archetype.
4. **5.1.2 Data Use and Sharing.** You would be collecting a credential that authenticates a person to a third party. Server-side storage builds an account-takeover honeypot, and the App Privacy label answer that honestly describes it reads catastrophically.
5. **Disney/ESPN terms** bar accessing the service by automated means and bar commercial use — as the sibling platform plan (`design/plan/platform.md`) independently documents from the terms themselves.

**What can ship instead:** a manual import path where the user supplies their own roster (paste, upload, or type), fully user-initiated, with no stored credential — and a plain sentence on the sign-up screen saying ESPN leagues do not get background digests. That is honest, it satisfies 4.2.3(i), and it needs no authorisation from anyone.

### What must be in the review notes

Write this before you need it:

- Every third-party service the app reads, named, with what data and why.
- **Sleeper:** written permission attached (the email).
- **Yahoo:** OAuth app registration details, the approved-access confirmation, and a pointer to the visible "Fantasy data provided by Yahoo Fantasy" attribution in the UI.
- **ESPN:** an explicit statement that the app does **not** read ESPN, does not store ESPN credentials, and that any ESPN league data present was entered manually by the user. Say it unprompted. A reviewer who finds "ESPN" in your league picker and no explanation will assume the worst.
- A demo account whose league renders **every page in full** — not in the degraded state. A reviewer who lands on a page reading "NO-DATA" will not read it as an honesty contract; they will read it as an incomplete app under 2.1.
- The 4.2 demo video.

**What authorisation Apple would expect on request:** a written grant from the service — a licence, a signed letter, or an email from an authorised person at the vendor — attached in the App Review Information section. Public availability of an endpoint is not authorisation, and Apple has rejected apps over exactly that distinction even where the third party permits general public use.

---

## 6. Gambling, contests, and the age rating

### Which guidelines actually touch this

> **5.3 Gaming, Gambling, and Lotteries.** Gaming, gambling, and lotteries can be tricky to manage and tend to be one of the most regulated offerings on the App Store. Only include this functionality if you've fully vetted your legal obligations everywhere you make your app available and are prepared for extra time during the review process.
>
> **5.3.1** Sweepstakes and contests must be sponsored by the developer of the app.
> **5.3.2** Official rules for sweepstakes, contests, and raffles must be presented in the app and make clear that Apple is not a sponsor or involved in the activity in any manner.
> **5.3.3** Apps may not use in-app purchase to purchase credit or currency for use in conjunction with real money gaming of any kind.
> **5.3.4** Apps that offer real money gaming (e.g. sports betting, poker, casino games, horse racing) or lotteries must have necessary licensing and permissions in the locations where the app is used, must be geo-restricted to those locations, and must be free on the App Store.

— [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), accessed 9 Sep 2026

**Does "advice about fantasy football" trigger 5.3? No.** The app takes no wagers, holds no currency, awards no prizes, runs no contest of its own, and sells no credit. 5.3.4 requires *real money gaming*; 5.3.1/5.3.2 require the developer to be *sponsoring* a contest. None applies. Two adjacent rules do apply if the product ever changes shape:

- **3.1.1** — if you ever unlock premium content, it must go through in-app purchase. "Apps may not use their own mechanisms to unlock content or functionality, such as license keys…"
- **5.3** *would* engage the moment the app displays odds, lines, spreads, or DFS pricing, or links out to a sportsbook. Keep all four off the roadmap unless you are prepared for the licensing work.

### The age rating — where this actually bites

Apple overhauled age ratings on **24 July 2025**, adding **13+, 16+ and 18+** to the existing 4+ and 9+, adding new questionnaire sections on in-app controls, capabilities, medical/wellness topics and violent themes, and requiring every developer to answer the updated questions by **31 January 2026** ([Apple Developer News](https://developer.apple.com/news/?id=ks775ehf); [Upcoming Requirements](https://developer.apple.com/news/upcoming-requirements/)). The questionnaire has since gained social-media capability questions too.

Apple's definitions ([Age ratings values and definitions](https://developer.apple.com/help/app-store-connect/reference/app-information/age-ratings-values-and-definitions/), accessed 9 Sep 2026):

> **Gambling:** Betting or wagering using real money or in-game currency that may be exchanged for real money. *May include: casino or card games, sports and non-sports betting, or lotteries and raffles.*
> **Simulated Gambling:** Betting or wagering without using real money or in-game currency that can be exchanged for real money.
> **Contests:** Events that allow users to compete with one another for rankings, rewards, or the achievement of personal goals. *May include: skill-based competitions, trivia quizzes, or sport or fitness contests.*

| Answer | Resulting rating |
|---|---|
| Contests — Infrequent | 4+ |
| Loot Boxes | 9+ |
| Contests — Frequent | **13+** |
| Simulated Gambling — Infrequent | 13+ |
| Gambling | 18+ |
| Simulated Gambling — Frequent | 18+ |

**The defensible answers for this app:**

- **Gambling: No.** No real money, no currency exchangeable for money.
- **Simulated Gambling: No.** The app hosts no wagering mechanic at all. It advises on a league hosted elsewhere.
- **Contests: Yes, Frequent.** A fantasy league is precisely "users compet[ing] with one another for rankings," and it is the app's entire subject — "infrequent" would be a stretch you'd have to defend.

**Expected rating: 13+.**

Sanity-check against the shelf: ESPN Fantasy is 13+; Yahoo Fantasy is 18+ with a Gambling descriptor; Sleeper is 18+ with Gambling and Simulated Gambling. Those apps *host* leagues and carry betting-adjacent products. This one hosts nothing and wagers nothing, so 13+ is both honest and defensible — but note that a rating a reviewer thinks is too low is a metadata rejection, and 13+ costs you nothing in reach. **Do not claim 4+.**

Two more choices that follow:

- **Category: Sports.** Not Games, not Entertainment. Apps in Games or Entertainment, and apps with Frequent/Intense Simulated Gambling, pick up an additional Korea regional rating; Sports avoids it and puts you next to the right peers.
- **2.3.7** warns that subtitles "should not include inappropriate content, reference other apps, or make unverifiable product claims." The project's own honesty contract already forbids the kind of copy that gets rejected here — "win your league" is an unverifiable product claim. Extend the contract to the App Store listing.

---

## 7. The build choice

### What makes this app's answer different from the generic one

Three facts change the usual calculus and should be held in mind through the whole comparison:

1. **There is no client-side app.** The pages are *pre-rendered static HTML*. No JS framework, no API the phone calls to construct a UI. The "app" is a bundle of files plus a delivery mechanism.
2. **The design system is a Python module.** `engine/ui.py` owns the tokens, 27 icons, verdict chips, meters, sheets, the 5-step type scale, three-state theming validated at import time, and a test suite; `engine/prefs.py` adds three themes, density, type size and quiet mode via a pre-paint boot script. It is finished, it passes a measured mobile checklist at 375/390/430px with zero horizontal overflow, and **it is the single best asset in the project.**
3. **The engine is Python 3.9, stdlib + PyYAML, and cannot run on iOS.** Every option below therefore requires a server that runs the renderers. That server is on the critical path *ahead of* any App Store date, and it does not exist yet.

### The comparison

| | (a) Capacitor | (b) React Native / Expo | (c) SwiftUI shell + WKWebView | (d) Fully native |
|---|---|---|---|---|
| **Existing HTML/CSS that survives** | ~100% | **~0%** | ~100% | **0%** |
| **`engine/ui.py` survives?** | Yes, whole | No — rewritten as RN StyleSheet | Yes, whole | No — redrawn in SwiftUI |
| **Dev-weeks to a submittable build** | 2–4 | 10–16+ | 4–8 | 16–24+ |
| **4.2 risk (bare)** | High | None | High | None |
| **4.2 risk (with Tier-1 native work)** | Medium | None | **Low** | None |
| **Toolchains to keep alive** | Xcode + Node + npm + CocoaPods + Capacitor | Xcode + Node + Expo SDK | **Xcode only** | Xcode only |
| **Weekly content change needs App Review?** | **No** (OTA of web assets permitted) | No (EAS Update) | No (bundle fetched from server) | **Yes, for any UI change** |
| **Maintenance for a non-developer** | Medium | High | Medium-low | Highest |

**(a) Capacitor.** Wraps the existing pages in a WKWebView and exposes native APIs through plugins. Everything `engine/ui.py` emits works unchanged — including the prefs boot script, because WKWebView *is* the same engine the pages were tuned against. Fastest to a build, and its standout advantage for a non-developer is that Apple permits over-the-air updates of the web layer (JavaScript and assets only, no native code changes), so weekly content changes never touch App Review. The costs: documented 4.2 rejections for Capacitor apps that lean on external services without enough native integration ([Capgo](https://capgo.app/blog/capacitor-ota-updates-app-store-approval-guide/), accessed 9 Sep 2026); a four-part JS toolchain to keep alive for years; and the widget still has to be written in Swift regardless, so you end up maintaining both stacks anyway.

**(b) React Native / Expo.** Renders real native views, so 4.2 evaporates. It also **deletes the best thing this project owns.** Every token, icon, chip, meter, sheet and type step in `engine/ui.py` would be re-authored in a second language — and then permanently maintained in parallel with the Python renderer that still produces `home.html` for the desktop and web path. Two design systems, guaranteed to drift, owned by someone who is not a JS developer. This is the correct answer for a team with a mobile engineer and a greenfield UI. It is the wrong answer here, and it is wrong for a reason that has nothing to do with React.

**(c) SwiftUI shell hosting WKWebView, with native push, offline and widgets.** Architecturally the same product as (a); the difference is who writes the shell. You get a native `TabView`, native sheets, native pull-to-refresh, WidgetKit, ActivityKit, App Intents and APNs *in one language, in one target, with no JS toolchain at all*. This is precisely the "webviews surrounded by native code" shape that reviewers accept. It costs a few weeks more than Capacitor up front and needs Swift help for the first build and for each iOS major — but in steady state it is one toolchain on Apple's own upgrade path, which matters enormously given Apple has already made Xcode 26 + the iOS 26 SDK mandatory for every upload since 28 April 2026. That is a hard, annual, forced toolchain upgrade; you want as few *other* toolchains riding on top of it as possible.

**(d) Fully native.** Zero 4.2 risk, four to six months, and the worst long-term outcome for this specific owner. It permanently forks the design system: every `ui.py` change needs a hand-written Swift twin, and the half he can regenerate himself with `./home.sh` stops being the half that ships. A non-developer would lose the ability to change his own product.

### Recommendation: **(c) the SwiftUI shell**, with **(a) Capacitor as the fallback if no Swift help is available**

Five reasons, in order of weight:

1. **It preserves `engine/ui.py` whole.** That module is a finished design system with a measured mobile acceptance bar, three-state theming, a preferences layer and tests. Options (b) and (d) throw it away and buy a permanent two-design-system maintenance tax. That is the decisive argument and nothing else comes close.
2. **The killer feature is native-only.** A Sunday-morning alert that must break through a Focus mode requires `UNNotificationInterruptionLevel.timeSensitive`. Both (a) and (c) can do it, but in (c) it lives in the same language as the widget, the Live Activity and the App Intent — which is where the rest of the 4.2 defence has to be built regardless.
3. **Offline is already paid for.** The pages are self-contained with zero network fetches at open, 3.3 MB across all eleven. Shipping them as an on-device bundle costs days, not weeks, and buys the strongest non-push 4.2 argument available.
4. **One toolchain.** For a non-developer maintaining this across seasons, Xcode alone is materially less to keep alive than Xcode + Node + npm + CocoaPods + Capacitor, each with independent breaking-change schedules.
5. **It is the lowest 4.2 risk of the two options that keep the HTML.** Native chrome that is genuinely native, rather than JS approximating native, is the difference a reviewer notices in the ninety seconds they spend.

Choose (a) instead if — and only if — Swift help cannot be found. Capacitor's plugin ecosystem then substitutes for the shell code you'd otherwise pay for, and its permitted OTA web-layer updates are a real ongoing advantage. Do not choose (b) or (d) for this product.

**The caveat that outranks the choice itself:** none of these ships without a server. The Python renderers must run somewhere other than the Mac, produce the bundle, and hold a device-token table. That is the sibling platform plan's Phase 1 and it sits ahead of every native week in the timeline below.

---

## 8. Push notifications

### What native push requires

| Requirement | Detail |
|---|---|
| **Paid membership** | Push is not in the free tier ([Apple, *Developer account overview*](https://developer.apple.com/support/compare-memberships/)). |
| **APNs auth key (.p8)** | Generated once in the developer portal, **downloadable exactly once** — lose it and you must revoke and regenerate. Token-based auth signs for every app on the team; keys don't expire. Since 2025 Apple also offers team-scoped (dev/prod) and topic-scoped (single bundle ID) keys. |
| **Alternative: .p12 certificate** | Per-app, expires annually. Don't. Use the .p8. |
| **Entitlement** | Push Notifications capability ticked on the App ID in Certificates, Identifiers & Profiles, **and** the capability enabled on the Xcode target (which writes the entitlements file). |
| **A server** | Something that holds the key, stores device tokens, and posts to APNs. **This project has none today.** |

Sources: [entrig.com, *How to Get an APNs .p8 Auth Key for iOS Push (2026)*](https://entrig.com/blog/apns-p8-key-file/); [Apple, UNNotificationInterruptionLevel](https://developer.apple.com/documentation/usernotifications/unnotificationinterruptionlevel) — all accessed 9 Sep 2026.

**The capability that matters most.** `UNNotificationInterruptionLevel.timeSensitive`: the system presents the notification immediately, lights up the screen, can play a sound, and **breaks through system notification controls** — including Focus modes and scheduled/summarised delivery. Set it with `content.interruptionLevel = .timeSensitive`, or in the push payload as `"interruption-level": "time-sensitive"`. Unlike `.critical`, it does **not** require an approved entitlement ([Apple documentation](https://developer.apple.com/documentation/usernotifications/unnotificationinterruptionlevel/timesensitive), accessed 9 Sep 2026).

Native also unlocks: silent/background pushes to pre-fetch the bundle before the visible alert lands, push-updated Live Activities, notification actions in the banner, rich notifications via a Content Extension, badge counts, and widget timeline reloads triggered by the push.

### What iOS Web Push gives an installed PWA

| | |
|---|---|
| **Added in** | iOS and iPadOS **16.4**, announced by WebKit on **16 February 2023** ([WebKit blog](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)). |
| **Requires** | A web app manifest with `display` set to `standalone` or `fullscreen`; the web app **added to the Home Screen**; and permission requested "in response to direct user interaction — such as tapping on a 'subscribe' button provided by the web app." |
| **Does not require** | Apple Developer Program membership. |
| **Behaves like** | Native notifications: "They show on the Lock Screen, in Notification Center, and on a paired Apple Watch," and integrate with Focus modes. |
| **Not available to** | An open Safari tab. The Push API on iOS is Home-Screen-web-app only. |
| **Later addition** | **Declarative Web Push** in iOS/iPadOS **18.4** (WebKit, 27 March 2025) — removes the service-worker requirement; badging on Home Screen web apps only where the Badging API is supported. |

*A note on the EU.* Several 2026 third-party pages still claim web push is unavailable in the EU. That is stale: Apple announced in February 2024 that iOS 17.4 would remove Home Screen web apps in the EU, then **reversed on 1 March 2024** and confirmed they continue to work as before ([9to5Mac](https://9to5mac.com/2024/03/01/apple-home-screen-web-apps-ios-17-eu/), [MacRumors](https://www.macrumors.com/2024/03/01/apple-walks-back-decision-to-disable-eu-web-apps/)). Not a US concern in any case.

### The honest judgement: "your starter was just ruled out, 90 minutes before kickoff"

**Can web push carry it? Technically, yes.** The message is one line of text that needs to arrive within minutes and be tappable into a page. All of that works on iOS 16.4+ for an installed home-screen web app, and the transport is Apple's own infrastructure — the same `*.push.apple.com` endpoints. For the weekend, this is the right call, and it will genuinely work.

**Should you believe it will land? Not reliably — and the gap is exactly where this alert lives.** Six things native buys that matter at 10:00 on a Sunday:

1. **Time Sensitive.** This is the whole argument. The single most common state for a phone on a Sunday morning is a Focus mode — Sleep, Personal, Do Not Disturb — or a Notification Summary. A native `timeSensitive` push breaks through both. A web push does not: it is *delivered* and can simply never be *seen* until the user picks the phone up. For an alert whose entire value is a 90-minute deadline, that is the difference between a feature working and a feature being decorative.
2. **Two acts before the first alert.** Web push needs the user to install to the Home Screen *and then* tap a subscribe button. Native asks once, in a system dialog, on first launch. Every extra step is subscribers you never get.
3. **No silent/background push.** You cannot pre-warm the bundle before the alert lands, so the tap opens a page that must then fetch — on a stadium network, at the worst possible moment.
4. **No notification actions, no Live Activity, no push-triggered widget reload.** The banner can only say the thing; it cannot let you act on it.
5. **Lower reported delivery reliability** than native, with recurring anecdotes of subscriptions silently dying ([MagicBell](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide), accessed 9 Sep 2026). You must monitor delivery rates and cannot treat silence as "no news."
6. **Uninstalling the home-screen icon kills the subscription with no server-side signal.** You will not know you stopped reaching someone.

**Verdict.** Web push is a real feature and it is the right answer for this weekend. But for the product's flagship promise, native push is not a nice-to-have — **`timeSensitive` *is* the feature.** State it that way in the roadmap, and do not let the PWA's success this season blur the distinction.

**Regardless of platform: keep an SMS or email fallback for the ruled-out alert.** It is the one notification where a missed delivery is the entire loss, and neither push channel guarantees arrival.

---

## 9. App Store Connect checklist

Everything needed for a first submission. Items marked **[BLOCKER]** will stop the submission button.

### Account and build

- [ ] **[BLOCKER]** Apple Developer Program membership, $99/year, active.
- [ ] **[BLOCKER]** Built with **Xcode 26 or later using the iOS 26 SDK or later** — mandatory for all uploads since **28 April 2026** ([Apple, Upcoming Requirements](https://developer.apple.com/news/upcoming-requirements/)). Note that apps built against the iOS 26 SDK get the Liquid Glass treatment on native UI components by default; check the design system against it.
- [ ] Bundle ID registered; **Push Notifications capability ticked** on the App ID and on the Xcode target.
- [ ] APNs `.p8` auth key generated and stored somewhere it cannot be lost (one download only).
- [ ] SKU, primary language, content rights declaration (this app displays third-party content — answer yes and hold the permissions).

### Metadata

- [ ] **[BLOCKER]** App name — "at least two characters and no more than 30 characters."
- [ ] Subtitle — "can't be longer than 30 characters." No unverifiable claims (2.3.7).
- [ ] **[BLOCKER]** Keywords — 100 characters, comma-separated. No trademarks, no competitor app names, no pricing.
- [ ] **[BLOCKER]** Description. Lead with the accuracy ledger — it is the 4.3(b) answer.
- [ ] Promotional text (editable without a new build — useful for weekly notes).
- [ ] **[BLOCKER]** Copyright.
- [ ] **[BLOCKER]** Primary category: **Sports**.
- [ ] **[BLOCKER]** Support URL — must lead to actual contact information (an email address at minimum).
- [ ] Marketing URL — optional.

### Privacy

- [ ] **[BLOCKER]** **Privacy Policy URL.** Required in App Store Connect *and*, per 5.1.1, linked "within the app in an easily accessible manner." The policy must "clearly and explicitly" identify what data is collected, how, and all uses; confirm equal protection by any third party it is shared with; and "explain its data retention/deletion policies and describe how a user can revoke consent and/or request deletion."
- [ ] **[BLOCKER]** **App Privacy "nutrition label."** Apple's definition of collection: > "'Collect' refers to transmitting data off the device in a way that allows you and/or your third-party partners to access it for a period longer than what is necessary to service the transmitted request in real time." **On-device-only processing is not collection.**

  Answers for this app, assuming a hosted v1 with accounts:

  | Data type | Collected? | Linked to you? | Purpose |
  |---|---|---|---|
  | Identifiers → User ID | Yes | Yes | App Functionality |
  | Contact Info → Email Address | Yes | Yes | App Functionality (login, digest) |
  | User Content → Other User Content (roster, league config) | Yes | Yes | App Functionality |
  | Usage Data → Product Interaction | **Only if you add analytics.** Ship without, answer No. | — | — |
  | Diagnostics → Crash Data | Only if you add a crash reporter | No | App Functionality |
  | Location (precise or coarse) | **No** | — | — |
  | Financial Info / Purchases | Only if you sell — via IAP | — | — |
  | **Data Used to Track You** | **NO.** No ad networks, no data brokers. | — | — |

  Answering **no** to tracking means no App Tracking Transparency prompt, and it is a genuine product differentiator. Protect it. Note the label covers third-party SDKs too — every SDK you add changes these answers, and so does the privacy policy.

  "Data Not Collected" is only available if v1 is genuinely local-only with no account. It stops being available the moment a server stores a roster.

### Age rating

- [ ] **[BLOCKER]** Complete the **updated** age rating questionnaire (mandatory for all apps since 31 Jan 2026). Gambling: **No**. Simulated Gambling: **No**. Contests: **Yes, Frequent**. Expected result: **13+**. See [§6](#6-gambling-contests-and-the-age-rating).

### Assets

- [ ] **[BLOCKER]** **App icon: exactly 1024×1024 px, PNG, fully opaque, no alpha channel.** An alpha channel where every pixel is opaque still triggers "Invalid Large App Icon" at upload. If you use Icon Composer, turn off blur on all layers — it is a known source of the alpha error ([developer.apple.com/forums/thread/795411](https://developer.apple.com/forums/thread/795411)).
- [ ] **[BLOCKER]** **Screenshots.** Per Apple's [screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/screenshot-specifications/): **1 to 10** per localization; `.jpg`/`.jpeg`/`.png`; **no alpha channels or transparencies.**
  - **iPhone (required if the app runs on iPhone):** 6.9" display — 1320×2868, 1290×2796, or 1260×2736 portrait — **or** 6.5" display (1284×2778 or 1242×2688) as the accepted alternative.
  - **iPad (required if the app runs on iPad):** 13" display — 2064×2752 or 2048×2732 portrait.
  - Missing smaller sizes are auto-scaled from the accepted size.
  - **Decide now: ship iPhone-only.** If the app declares iPad support you *must* supply 13" iPad screenshots or App Store Connect blocks the submission. Given that "mobile is the acceptance bar," iPhone-only is both faster and more honest for v1.
  - **Recommended six:** (1) Lineup verdicts, (2) the board, (3) the trade desk, (4) **the Time Sensitive alert on a lock screen**, (5) **the widget on a home screen**, (6) the sources/receipts page. Shots 4 and 5 are doing double duty as the 4.2 argument.

### App Review Information

- [ ] **[BLOCKER]** Contact first/last name, phone, email.
- [ ] **[BLOCKER]** **Demo account** username and password — 2.1(a): "include demo account info (**and turn on your back-end service!**) if your app includes a login." The demo league must render every page in full, not degraded. Test it from a signed-out device the morning you submit.
- [ ] **[BLOCKER]** **Notes for Review**, written with specificity — 2.3.1(a): "generic descriptions will be rejected." Cover: the native feature list, the third-party data statement (Sleeper / Yahoo / *not* ESPN), and how to exercise every feature.
- [ ] **Attachment:** the Sleeper written permission, the Yahoo API access confirmation, and the 30-second demo video of the Time Sensitive push and the widget.

### Export compliance

- [ ] **[BLOCKER]** The app uses only HTTPS via `URLSession`/`WKWebView` — encryption built into the operating system, which is **exempt** from export documentation requirements ([Apple, *Complying with Encryption Export Regulations*](https://developer.apple.com/documentation/security/complying-with-encryption-export-regulations)). Set `ITSAppUsesNonExemptEncryption = false` in `Info.plist` to answer it once and stop the per-build prompt.
  **Caveat, and it is a real one:** this is a regulatory declaration logged against your developer account and the distributed binary, not a UI annoyance to dismiss. It is only correct while you add no proprietary cryptography. Re-examine it if you ever encrypt the on-device bundle yourself.

### Distribution

- [ ] Pricing and availability (free).
- [ ] Version release settings (manual release is safer for a first launch — you choose the moment).
- [ ] **TestFlight** before any App Store submission: **up to 100 internal testers** (App Store Connect users, no Beta App Review, builds available in minutes) and **up to 10,000 external testers** (first build of each version goes to Beta App Review automatically when added to a group). **Builds are available for 90 days.**

---

## 10. Week-by-week timeline

Dated, pessimistic, and assuming the owner is not writing the Swift himself. Anchored to Wednesday 9 September 2026.

| Week | Dates | Work | Gate cleared |
|---|---|---|---|
| **0** | Wed 9 – Sun 13 Sep | **PWA ships for week 1** (other agent). On the native track, *paperwork only*: enrol as an **individual** ($99); **email Sleeper** for commercial permission; **file the Yahoo Fantasy Sports API application**. | Longest-lead, no-SLA items started before any code. |
| **1** | 14 – 20 Sep | Enrolment likely clears. Register the bundle ID, tick Push Notifications, generate and safely store the APNs `.p8`. Decide iPhone-only. **Write the privacy policy and stand up the support URL** — both are just pages, both are hard blockers later, both are free to do now. | Membership; APNs key. |
| **2–3** | 21 Sep – 4 Oct | **The server.** The Python renderers must run off the Mac, emit the page bundle, and hold a device-token table. This is the real gate — nothing native works without it. (Sibling plan's Phase 1.) | Hosting; token store. |
| **4–6** | 5 – 25 Oct | **The SwiftUI shell.** `TabView`, WKWebView host, on-device bundle + offline-first, native pull-to-refresh, native sheets mapped from the design system's `sheet` component, share sheet, Face ID lock, universal links. | A running app on a real phone. |
| **7–8** | 26 Oct – 8 Nov | **Push end-to-end**, including `timeSensitive`, wired to the real injury feed. **WidgetKit widget.** App Intents / Shortcuts. This is the 4.2 evidence, so it is not cuttable scope. | The killer feature; the 4.2 defence. |
| **9** | 9 – 15 Nov | App Store Connect fill-out: metadata, six screenshots, icon, privacy label, age rating, review notes with the Sleeper/Yahoo evidence attached. **TestFlight internal** build to the owner's phone. | Submittable metadata. |
| **10** | 16 – 22 Nov | **TestFlight external** to both leagues (first build per version goes to Beta App Review). Fix what real Sundays break. | Real users, real push, real bugs. |
| **11** | 23 – 29 Nov | **First App Store submission.** | Submitted. |
| **12–13** | 30 Nov – 13 Dec | **Budget two rejection rounds.** Realistic first-approval window. | **Live.** |

**Realistic live date: mid-December 2026 — NFL week 14–15, the fantasy playoffs. Pessimistic: January 2027, i.e. the offseason.**

Two things that move this earlier, and one that moves it later:

- **Earlier:** treat **TestFlight external as the season's channel** and skip the App Store until the offseason. That is live around **week 10 (mid-November)** with real push and a real home-screen icon, and it removes App Review from the critical path entirely. For two private leagues this is arguably the correct product decision, not a compromise. Budget a re-upload every 90 days.
- **Earlier:** choose **Capacitor** instead of the SwiftUI shell and weeks 4–6 compress to roughly 2–3 — at the cost of a higher 4.2 risk and a four-part toolchain forever.
- **Later:** if the Yahoo application stalls, or Sleeper declines commercial permission, the binary loses a data source and §5's paperwork becomes the schedule. That is precisely why week 0 is paperwork.

---

## 11. Top five rejection risks

**1. Guideline 4.2 — minimum functionality, and 4.2.2's "content aggregators."**
*Likelihood: high. Cost: 2–6 weeks.* This is the one that will actually happen if you submit early.
**Mitigations:** ship the full Tier-1 native list before first submission — APNs push at `timeSensitive`, genuine on-device offline, native `TabView` and sheets, a WidgetKit widget, and the share sheet — plus App Intents. Write review notes that name the app's *own computation* (VBD replacement baselines, the survival model, tier assignment, the graded accuracy ledger) rather than the sources it reads. Attach a 30-second screen recording of the Time Sensitive alert firing and the widget updating from it. Make screenshots 4 and 5 the lock-screen alert and the home-screen widget, so the 4.2 argument is visible before a reviewer opens the binary. Keep the account in your own name so 4.2.6 (template services) never engages.
*Running alongside it:* **4.3(b)**, tightened 8 June 2026 against apps "indistinguishable from what's already widely available." Answer it with the accuracy ledger — a public, graded scorecard no competitor ships — stated in the first line of the description.

**2. Guideline 5.2.2 — third-party data, triggered by ESPN.**
*Likelihood: high if an ESPN feature ships. Cost: the feature, or the account.*
**Mitigations:** **no ESPN read in the binary, ever** — no stored cookie, no automated fetch, manual user-entered import only. Attach the Sleeper written permission and the Yahoo API access confirmation to App Review Information. Put the required "Fantasy data provided by Yahoo Fantasy" attribution in the UI *before* submitting. State the ESPN position unprompted in the review notes. Never fabricate an authorisation document — that is account termination, not a rejection.

**3. Guideline 2.1 — App Completeness: no working demo, or a degraded demo.**
*Likelihood: medium. Cost: 1–3 days per round.* This project has a specific, unusual exposure: it is *designed* to degrade honestly and print "NO-DATA" when it doesn't know something. A reviewer reads that as an incomplete app, not as an honesty contract.
**Mitigations:** maintain a permanent reviewer account on a seeded league that renders **every page in full**, with the backend guaranteed up through the review window. Test it from a signed-out device the morning of submission. If any page can still show a degraded state, explain in the review notes — in one sentence — that honest degradation is a deliberate product behaviour, and point at a page that demonstrates the full state.

**4. Age rating and metadata mismatch (2.3.x, and the 5.3 halo).**
*Likelihood: medium. Cost: 1–3 days per round.*
**Mitigations:** answer Gambling **No**, Simulated Gambling **No**, Contests **Yes/Frequent** → **13+**. Do not claim 4+. Category **Sports**, not Games or Entertainment. No odds, lines, spreads, DFS pricing or sportsbook links anywhere in the app or the metadata — any one of them pulls 5.3 into scope and adds review time by Apple's own warning. No unverifiable win claims in the name, subtitle, description or screenshots; the project's honesty contract already forbids the copy that gets rejected here, so extend it to the listing.

**5. Guideline 5.1.1 — privacy policy and App Privacy label mismatch.**
*Likelihood: medium. Cost: 1–3 days per round, and it recurs on every update.*
**Mitigations:** write the privacy policy **from** the nutrition-label answers, not the other way round, so the two cannot disagree. Include retention and deletion policy and a working deletion path — 5.1.1 requires you to "describe how a user can revoke consent and/or request deletion." Link the policy inside the app "in an easily accessible manner," not only in App Store Connect. Answer **No** to Data Used to Track You and keep it true — it avoids the ATT prompt entirely and it is a genuine differentiator. Re-check both documents after **every** SDK addition; an analytics or crash SDK silently changes the correct answers.

*Runners-up, worth a line each:* **4.2.3(i)** (an app that needs another app to function — the ESPN cookie flow); **2.3.1(a)** generic review notes, which Apple says will be rejected outright; and **4.5.3**, added 8 June 2026, if Live Activities ever drift from the live matchup into anything promotional.

---

## Evidence

Every URL below was accessed **9 September 2026**. Reddit was not used.

### Apple — primary

| Claim | Source |
|---|---|
| $99/year; individual vs organisation requirements; D-U-N-S, binding authority, work email, website | [Become a member — Apple Developer Program](https://developer.apple.com/programs/enroll/) |
| Organisation must wait for verification before purchasing; notarized documents; 24-hour purchase-confirmation line | [Enrollment — Membership — Account — Help](https://developer.apple.com/help/account/membership/program-enrollment/) |
| "allow up to 5 business days to receive your number from D&B"; "up to 2 business days for Apple to receive your information"; two-week escalation | [D-U-N-S Number — Membership — Account — Help](https://developer.apple.com/help/account/membership/D-U-N-S/) |
| Individual enrolment via the Apple Developer app | [Enrolling, verifying, and renewing with the Apple Developer app](https://developer.apple.com/help/account/membership/enrolling-in-the-app/) |
| Free account vs paid: App Store distribution, TestFlight, App Store Connect, push all require membership; personal-team 7-day profile expiry, 10 App IDs, 3 devices | [Developer account overview](https://developer.apple.com/support/compare-memberships/) |
| "On average, 90% of submissions are reviewed in less than 24 hours." | [App Review — Distribute](https://developer.apple.com/distribute/app-review/) |
| Guidelines 4.2 / 4.2.1 / 4.2.2 / 4.2.3, 4.1, 4.2.6, 4.3(a), 4.3(b), 4.5.1, 5.1.1, 5.1.2, 5.2.1, 5.2.2, 5.3–5.3.4, 2.1, 2.3.1, 2.3.7, 2.3.10, 3.1.1 | [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) |
| Guidelines revised **8 June 2026**: 1.2, 4.3(a), 4.3(b), 4.5.3; License Agreement changes | [Updated Apple Developer Program License Agreement and App Review Guidelines now available](https://developer.apple.com/news/?id=a233fmpw) |
| Guidelines revised **6 February 2026**: random/anonymous chat under 1.2 | [Updated App Review Guidelines now available](https://developer.apple.com/news/?id=d75yllv4) |
| Age rating overhaul announced **24 July 2025**: 13+/16+/18+ added, new question sets, 31 Jan 2026 deadline | [Updated age ratings in App Store Connect](https://developer.apple.com/news/?id=ks775ehf) |
| Age rating questionnaire gained social-media questions | [Age rating questionnaire now includes social media questions](https://developer.apple.com/news/?id=tlur8uvi) |
| Gambling / Simulated Gambling / Contests definitions and the rating each produces | [Age ratings values and definitions](https://developer.apple.com/help/app-store-connect/reference/app-information/age-ratings-values-and-definitions/) |
| **Since 28 April 2026:** uploads must use Xcode 26 + iOS 26 SDK. **Since 31 Jan 2026:** updated age-rating answers required | [Upcoming Requirements](https://developer.apple.com/news/upcoming-requirements/) |
| Screenshots: 1–10, no alpha; 6.9" required (1320×2868 / 1290×2796 / 1260×2736) or 6.5" alternative; 13" iPad required if the app runs on iPad | [Screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/screenshot-specifications/) |
| Name ≤30 chars; subtitle ≤30 chars; required fields incl. Privacy Policy URL, Age Rating, App Review Information | [App information](https://developer.apple.com/help/app-store-connect/reference/app-information/) · [Required, localizable, and editable properties](https://developer.apple.com/help/app-store-connect/reference/required-localizable-and-editable-properties/) |
| App Privacy: definition of "collect", tracking, linked/not-linked; the data-type categories | [App Privacy Details](https://developer.apple.com/app-store/app-privacy-details/) |
| `timeSensitive`: presents immediately, lights the screen, breaks through system notification controls; `.critical` needs an entitlement, `.timeSensitive` does not | [UNNotificationInterruptionLevel](https://developer.apple.com/documentation/usernotifications/unnotificationinterruptionlevel) · [.timeSensitive](https://developer.apple.com/documentation/usernotifications/unnotificationinterruptionlevel/timesensitive) |
| HTTPS via `URLSession` is exempt encryption | [Complying with Encryption Export Regulations](https://developer.apple.com/documentation/security/complying-with-encryption-export-regulations) |
| TestFlight: 100 internal / 10,000 external; first build per version to Beta App Review; 90-day build availability | [TestFlight](https://developer.apple.com/testflight/) · [TestFlight overview — App Store Connect Help](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview) |
| Web Push added in iOS/iPadOS 16.4; manifest + Home Screen + user gesture; Lock Screen / Notification Center / Apple Watch; no membership required (16 Feb 2023) | [Web Push for Web Apps on iOS and iPadOS — WebKit](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/) |
| Declarative Web Push on iOS/iPadOS 18.4, no service worker, badging caveat (27 Mar 2025) | [Meet Declarative Web Push — WebKit](https://webkit.org/blog/16535/meet-declarative-web-push/) |
| Real 2026 enrolment stalls of 3+ weeks | [Forum thread 817247](https://developer.apple.com/forums/thread/817247) · [Forum thread 821717](https://developer.apple.com/forums/thread/821717) |
| 5.2.2 rejections require documentary evidence attached in App Review Information | [Forum thread 134224](https://developer.apple.com/forums/thread/134224) · [Forum thread 105345](https://developer.apple.com/forums/thread/105345) |
| Icon alpha-channel failures, incl. the Icon Composer blur bug | [Forum thread 795411](https://developer.apple.com/forums/thread/795411) |

### Third-party vendors — primary

| Claim | Source |
|---|---|
| "free to use for non-commercial purposes"; "For commercial use … please reach out to us directly to discuss licensing"; no token; <1000 calls/min | [Sleeper API docs](https://docs.sleeper.com/) |
| Yahoo API application: product description, data needed, user base, 3–6 month user estimate; "Each application is reviewed by the Yahoo Fantasy Sports team"; read-only by default | [Apply for Yahoo Fantasy Sports API](https://sports.yahoo.com/developer/access/) |
| Yahoo OAuth 2.0; attribution "Fantasy data provided by Yahoo Fantasy" linking back | [Yahoo Fantasy Sports API docs](https://sports.yahoo.com/developer/docs/) · [Getting Started](https://yahoofantasysportsapidocs.readthedocs.io/guide/GettingStarted/) |
| ESPN has no sanctioned public fantasy API; private leagues require the user's own `SWID` and `espn_s2` cookies | [cwendt94/espn-api](https://github.com/cwendt94/espn-api) |

### Secondary — practitioner reporting, used only where Apple publishes nothing

| Claim | Source |
|---|---|
| 2026 review-time variance; "Waiting for Review" running 3–7 days; new apps slower than updates | [AppCompliance — How Long Does App Store Review Take in 2026](https://appcompliance.io/blog/app-store-review-time-2026/) |
| Mac App Store review times lengthening; submission volume up on AI-generated apps | [Michael Tsai, 2 Mar 2026](https://mjtsai.com/blog/2026/03/02/mac-app-store-review-times-increasing/) |
| 4.3(b) tightened against apps that "do not add value"; implications for wrapper apps (9 Jun 2026) | [9to5Mac](https://9to5mac.com/2026/06/09/apple-tightens-app-review-guidelines-against-apps-that-do-not-add-value-to-the-app-store/) |
| What webview apps need to pass 4.2 in practice: native navigation, APNs, offline handling | [MobiLoud](https://www.mobiloud.com/blog/app-store-review-guidelines-webview-wrapper) · [Median.co](https://median.co/blog/will-apple-approve-my-webview-app) |
| Documented Capacitor 4.2 rejections; OTA limited to JS and assets, no native code changes | [Capgo — Capacitor OTA Updates: App Store Approval Guide](https://capgo.app/blog/capacitor-ota-updates-app-store-approval-guide/) |
| Capacitor vs React Native architecture and effort for an existing web app | [PkgPulse](https://www.pkgpulse.com/guides/react-native-vs-expo-vs-capacitor-cross-platform-mobile-2026) · [NextNative](https://nextnative.dev/blog/capacitor-vs-react-native) |
| APNs `.p8`: single download, never expires, team- and topic-scoped keys since 2025 | [entrig.com](https://entrig.com/blog/apns-p8-key-file/) |
| iOS web push reliability lower than native; subscriptions can silently die | [MagicBell — PWA iOS Limitations](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide) |
| Apple reversed the EU Home Screen web app removal on 1 March 2024 | [9to5Mac](https://9to5mac.com/2024/03/01/apple-home-screen-web-apps-ios-17-eu/) · [MacRumors](https://www.macrumors.com/2024/03/01/apple-walks-back-decision-to-disable-eu-web-apps/) |
| `ITSAppUsesNonExemptEncryption` is a regulatory declaration logged against the account, not a UI dismissal | [AppCompliance](https://appcompliance.io/blog/app-store-encryption-export-compliance/) |

### Measured in this repository, 9 September 2026

- Rendered page bundle: **3,481,998 bytes (3.32 MB)** across eleven HTML files — `home.html` 459,430 B; `board-espn-1-week1.html` 700,313 B; `board-yahoo-main-week1.html` 620,887 B; `tradedesk-espn-1-week1.html` 288,087 B; the rest 219–244 KB each. Small enough to ship on-device, which is what makes offline nearly free.
- `engine/ui.py` — the design system this decision protects: colour tokens validated to carry identical key sets across all three theme states at import time, 27 stroke icons on a 24×24 grid designed for 20px, `verdict_chip` / `matchup_meter` / `sheet` / `segmented` / `row3` / `legend_popover` components, `--wr-t0..t4` type scale.

---

*Nothing in `saves/`, `data/rosters/`, `leagues/` or `data/sources.yaml` was read for content or modified by this work. No engine module was touched.*
