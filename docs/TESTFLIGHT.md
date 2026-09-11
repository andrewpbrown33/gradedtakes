# TestFlight — from a build that runs on your iPhone to the league's phones

This is the whole path, in order, written to be followed with the mouse.
It assumes `ios/README.md` is done: Xcode is installed, your Team ID is in
`ios/project.yml`, and the app runs on your own iPhone from Xcode.

TestFlight is this season's distribution. Two tiers:

| | Internal testers | External testers |
|---|---|---|
| Who | People you add as users of your App Store Connect account | Anyone, by email or a public link |
| How many | up to 100 | up to 10,000 |
| Review | **None.** Build is testable minutes after processing | **Beta App Review** on the first build of each version (usually hours, up to ~48 h) |
| Use it for | You, first. Then one or two league-mates you trust to report bugs | The league |

**Every build expires 90 days after upload.** The season is longer than
that — §9 has the calendar.

Contents: 1 App ID · 2 APNs key · 3 App record · 4 Signing check · 5 Archive & upload · 6 Internal testers · 7 External testers & Beta App Review · 8 Test push · 9 The 90-day clock · 10 What testers see

---

## 1. Register the App ID and the App Group (once)

Xcode's automatic signing usually does this on the first build. Do it by
hand anyway — it takes five minutes and the App Store Connect record in
§3 cannot be created until the App ID exists.

Go to <https://developer.apple.com/account/resources/identifiers/list>
(sign in with the Developer Program Apple ID).

**The app:**

1. Click the blue **+** next to *Identifiers*.
2. Select **App IDs** → **Continue**. Select type **App** → **Continue**.
3. **Description:** `Graded Takes` (internal label, not shown to users).
4. **Bundle ID:** select **Explicit**, type `com.gradedtakes.app`.
5. In the **Capabilities** list, tick:
   - **App Groups**
   - **Push Notifications**
   - **Time Sensitive Notifications**
6. **Continue** → **Register**.

**The widget:**

7. **+** again → App IDs → App → Description `Graded Takes Widget`, Explicit
   Bundle ID `com.gradedtakes.app.widget`, tick **App Groups** only →
   Continue → Register.

**The App Group:**

8. **+** again → this time select **App Groups** → **Continue**.
9. Description `Graded Takes shared`, Identifier `group.com.gradedtakes.app`
   → **Continue** → **Register**.

**Attach the group to both App IDs:**

10. Back in the Identifiers list, click **Graded Takes** (com.gradedtakes.app)
    → next to **App Groups** click **Configure** (or **Edit**) → tick
    `group.com.gradedtakes.app` → **Continue** → **Save**. If it warns
    that existing provisioning profiles will be invalidated, click
    **Confirm** — Xcode makes new ones.
11. Same for **Graded Takes Widget**.

Those three identifiers match `ios/project.yml` and the two
`.entitlements` files exactly. Do not rename any of them.

## 2. Create the APNs key — the `.p8` file (once, downloadable once)

This key signs every push you ever send. Apple lets you download it
exactly once; lose it and you revoke and make another.

1. <https://developer.apple.com/account/resources/authkeys/list> →
   blue **+** next to *Keys*.
2. **Key Name:** `Graded Takes APNs`.
3. Tick **Apple Push Notifications service (APNs)** → click **Configure**
   on that row.
4. **Environment:** *Sandbox & Production*. **Key Restriction:** *Topic
   Specific* → tick `com.gradedtakes.app` → **Save**.
5. **Continue** → **Register**.
6. The page shows the **Key ID** (10 characters). Write it down. Click
   **Download**. The file `AuthKey_<KEYID>.p8` lands in Downloads. Click
   **Done**.

Now put it somewhere safe and *out of the repository*:

```
mkdir -p ~/secrets && chmod 700 ~/secrets
mv ~/Downloads/AuthKey_*.p8 ~/secrets/
chmod 600 ~/secrets/AuthKey_*.p8
ls -l ~/secrets
```

Then back it up once to somewhere encrypted you will still have in a year
(a password manager's file attachment, or an encrypted disk image). Not
email, not iMessage, not the repo.

The repo's `.gitignore` blocks `*.p8` everywhere. Prove it — this must
print the ignore rule, not nothing:

```
touch ios/AuthKey_TEST.p8 && git check-ignore -v ios/AuthKey_TEST.p8; rm ios/AuthKey_TEST.p8
```

Three values you will need later, all safe to write in a notes file:
**Team ID** (Membership details), **Key ID** (from step 6), and the path
`~/secrets/AuthKey_<KEYID>.p8`. The key's *contents* are the secret.

The server that sends the real "ruled out" pushes needs the same three
things. It is the only other place the key ever goes.

## 3. Create the app record in App Store Connect (once)

1. <https://appstoreconnect.apple.com> → **My Apps** → blue **+** (top-left)
   → **New App**.
2. Fill the sheet:
   - **Platforms:** tick **iOS** only.
   - **Name:** `Graded Takes`. This is the App Store name (2–30
     characters) and must be unique across the whole store. If Apple says
     it is taken, try `Graded Takes — Fantasy` or `Graded Takes Fantasy`;
     the name on the phone stays "Graded Takes" regardless (that comes
     from the app itself).
   - **Primary Language:** English (U.S.).
   - **Bundle ID:** pick **Graded Takes – com.gradedtakes.app** from the
     dropdown. (Not there? §1 was not finished, or wait a minute and reload.)
   - **SKU:** `gradedtakes-ios-2026`. Internal, never shown, cannot be
     changed later.
   - **User Access:** **Full Access**.
3. **Create.**

You land on the app's page. Nothing else on it is needed for *internal*
testing. External testing asks for a **Privacy Policy URL** in its Test
Information sheet, and the App Store later requires one — so write it
now, it is short: a page on gradedtakes.com that says what the app stores
(the private link, in the phone's Keychain; the push token, on your
server; nothing else), that nothing is tracked or sold, and how to delete
it (remove the app; email you to drop the push token).

## 4. Check signing in Xcode

Open `ios/GradedTakes.xcodeproj`. Blue **GradedTakes** icon at the top of
the file list → **TARGETS → GradedTakes → Signing & Capabilities**:

- **Automatically manage signing** ticked, **Team** is you.
- The capability blocks read **App Groups** (`group.com.gradedtakes.app`
  ticked), **Push Notifications**, **Time Sensitive Notifications**.
- No red text. (Red text about a missing entitlement: `ios/README.md`,
  Troubleshooting.)

Then **TARGETS → GradedTakesWidget** → Team is you, App Groups ticked.

Bump the build number for this upload: in `ios/project.yml` set
`CURRENT_PROJECT_VERSION` one higher than last time, save, run
`./ios/generate.sh`, reopen Xcode. First upload: leave it at `1`.

## 5. Archive and upload

1. In the destination picker (top of the Xcode window, next to the scheme
   name *GradedTakes*) choose **Any iOS Device (arm64)** — under *Build*.
   You cannot archive against a simulator.
2. Menu **Product → Archive**. Two to five minutes. If it fails, the
   errors are in the left-hand issue navigator (⌘5); a signing error
   means §4, a Swift error means the Swift side.
3. When it finishes, the **Organizer** window opens on the **Archives**
   tab with today's archive selected. (Reopen any time: **Window →
   Organizer**.)
4. Click **Distribute App** (blue button, right side).
5. Choose **TestFlight & App Store** (older Xcode wording: *App Store
   Connect*) → **Distribute**. Xcode 15 and later does the rest with
   sensible defaults: upload symbols, manage version and build number
   (leave that unticked — the project owns the numbers), automatic
   signing. If it shows those as options, click **Next** / **Upload**.
6. Wait for **Upload Successful**. Click **Done**.

Within a few minutes Apple emails *"The status of your app has changed to
Processing"* and then *"…Ready to Test"* (up to half an hour; the build
appears under **TestFlight → iOS Builds** in App Store Connect meanwhile,
marked *Processing*).

Export compliance never asks, because `ITSAppUsesNonExemptEncryption` is
`false` in the app's Info.plist (`ios/project.yml`): the app uses only the
HTTPS built into iOS. That is a regulatory statement in your name — it
stays true only while nobody adds their own encryption to the app.

If the upload is rejected instead, the email names the code: **ITMS-90717**
*Invalid Large App Icon* means an alpha channel crept into the icon — run
`ios/tools/make_icon.sh` (it strips it) and re-archive; **ITMS-90473**
means the app and widget version numbers disagree — they cannot if you
only edit `project.yml`, so someone changed a version inside Xcode:
`generate.sh` and re-archive.

## 6. Internal testers: you first

1. App Store Connect → **My Apps → Graded Takes → TestFlight** tab.
2. Left sidebar, next to **Internal Testing**, click **+**.
3. **Group name:** `Owner`. Tick **Enable automatic distribution** (every
   future build goes to this group by itself). **Create**.
4. On the group page, next to **Testers**, click **+**. The list shows
   your App Store Connect users — you, at least. Tick yourself → **Add**.
5. Under **Builds**, the processed build is already there (automatic
   distribution). If not: **+** → pick the build → **Add**.

On the iPhone: install **TestFlight** from the App Store. Open the
invitation email (*"Andrew Brown has invited you to test Graded Takes"*)
→ **View in TestFlight** → **Accept** → **Install**. The app installs
alongside — or replacing — the Xcode-installed copy, with an orange dot
next to its name in TestFlight.

**This build talks to Apple's production push server**, unlike the
Xcode-installed one. §8 has the flag.

To add a trusted league-mate as an *internal* tester they must first be a
user of your App Store Connect account: **Users and Access** (top-right
menu under your name) → **+** → first name, last name, email → **Role:
Marketing** (internal testers must hold Account Holder, Admin, App
Manager, Developer or Marketing; Marketing is the one that cannot upload
builds or touch signing — do not give league-mates Admin) → **Apps:
Graded Takes** → **Invite**. They accept the Apple email, then appear in
the tester list in step 4. Fine for two or three people; for the whole
league use §7.

## 7. External testers: the league, and Beta App Review

External testing is the right tool for the league: nobody needs an App
Store Connect account, and a **public link** means you never have to
collect Apple IDs.

1. **TestFlight** tab → next to **External Testing** click **+**.
2. **Group name:** `League`. **Create.**
3. **Builds** section → **+** → select the build → **Next**.
4. **Test Information** — this is what Beta App Review reads. First time
   only, App Store Connect asks for all of it; later builds only ask
   *What to Test*.
   - **What to Test:** what changed and how to exercise every native
     feature. Be specific; generic text is the top rejection reason:
     > Paste your private link on first launch (a demo link is in the
     > notes below). Tap each of the five tabs along the bottom: Home,
     > Lineup, Board, Ledger, Trade Desk. Turn on Airplane Mode and
     > relaunch: the pages still open, with a gold-edged banner reading
     > "Offline — showing week N as of <date>" and a Retry button. Add
     > the "Needs you" widget (search "Graded Takes" in the home-screen
     > widget gallery; it also has a lock-screen size). Allow
     > notifications when asked; a Time Sensitive alert arrives when a
     > starter is ruled out, and tapping it opens the lineup it names.
   - **Beta App Description:** two sentences on what the app is
     (fantasy-football lineup verdicts, waiver board, trade desk, graded
     against results).
   - **Feedback Email:** yours.
   - **Marketing URL:** optional. **Privacy Policy URL:** the page from §3.
   - **Beta App Review Information:** your first name, last name, phone,
     email.
   - **Sign-in required:** the app has no username/password, so **No** —
     but the reviewer still needs to see content. In **Review Notes**
     paste a **demo private link** that renders every page in full (make a
     demo reader in `users.yaml` and publish it; do not hand over your own
     link). Test that link in Safari on a phone that morning.
   - **Notes:** the third-party-data statement from `docs/APPSTORE.md` §5
     and a sentence on the native features (native APNs push at the Time
     Sensitive level, offline cache, WidgetKit widget, share sheet), so
     nobody mistakes it for a web wrapper.
5. **Next** → **Submit for Review**. The build shows *Waiting for Review*
   → *In Review* → *Approved* (usually within a day; Apple allows up to
   48 h and occasionally longer at busy times). You get an email each step.
   A rejection email quotes the guideline — fix, bump the build number,
   re-upload, add to the group, resubmit.
6. Once approved, on the **League** group page enable **Public Link**
   (right-hand panel) → **Enable Public Link** → set a **tester limit**
   (league size plus a few, e.g. `20`) → copy the URL. Send it to the
   league group chat with one line: *install TestFlight from the App Store
   first, then open this link.*

   Or add testers by email instead: **Testers → +** → **Add New Testers**
   → email, first name, last name → **Add**. They get the invite email.

Later builds of the **same** version (say 1.0 build 3) usually do not go
through review again — Apple only re-reviews when it decides the changes
are significant. A new `MARKETING_VERSION` always goes through review.

Beta App Review applies the App Store guidelines, including 4.2 — the
native features are what get this app through, so *What to Test* must
walk the reviewer to each of them.

## 8. Send yourself a test push

You need the phone's **device token** — 64 hex characters the app receives
from Apple when it registers, and POSTs to your server on every launch
(`ios/GradedTakes/Push/Push.swift` documents the exact request). Read it
in the app: **Settings → Notifications → Device token** (long-press the
value to copy it; it says *Not yet* until Apple has answered). The
server's registration table has it too. It is not a secret, but it is
per-phone and per-install — a reinstall gets a new one.

```
python3 docs/send_test_push.py \
    --key ~/secrets/AuthKey_ABC123DEFG.p8 \
    --team-id AB12CD34EF \
    --device-token 0123456789abcdef…(64 hex)
```

Add **`--production`** when the app on the phone came from TestFlight or
the App Store. Leave it off for a build Xcode installed. This is the
single most common mistake: `400 BadDeviceToken` almost always means the
wrong environment, not a bad token.

The script signs a token with the `.p8` (using the Mac's `openssl`),
POSTs one alert over HTTP/2 (using the Mac's `curl`) with
`"interruption-level": "time-sensitive"`, and prints Apple's answer:

| Response | Meaning |
|---|---|
| `200 OK` | Delivered to Apple. On the phone within seconds. |
| `400 BadDeviceToken` | Wrong environment (add or remove `--production`), or a token from a deleted install. |
| `403 InvalidProviderToken` | Wrong `--team-id`, or the key id in the file name does not match the key. |
| `400 TopicDisallowed` | The key is Topic Specific and `com.gradedtakes.app` was not ticked when it was made. |
| `410 Unregistered` | The app was deleted from that phone. |

Prove Time Sensitive works: put the phone in **Do Not Disturb**, send the
push, and it still appears with sound. Then check iPhone **Settings →
Notifications → Graded Takes** — the **Time Sensitive Notifications**
toggle is what the user controls; if they switch it off, alerts wait
until the Focus ends, and there is nothing the server can do about it.

Optional arguments: `--title`, `--body`, `--path lineup-espn-1-week1.html`
(the page the app opens when the alert is tapped), `--week 3` (groups the
week's alerts together on the lock screen), `--needs 2` (also updates the
home-screen widget to "2 calls need you"), `--collapse-id` (a newer push
with the same id replaces the older one on the lock screen; default
`ruled-out`), `--expires-in` seconds (default 90 minutes — after kickoff
the alert is worthless, so Apple should stop trying), and `--silent` (the
invisible pre-fetch push that warms a page before the alert; nothing
shows on the phone, and Apple may hold it for a while). The payload shape
is the server contract written at the top of
`ios/GradedTakes/Push/Push.swift`; the real server sends the same thing.

## 9. The 90-day clock and the mid-season re-upload

A TestFlight build stops launching 90 days after it was *uploaded* (the
date is on the build in App Store Connect; testers see the countdown in
the TestFlight app). The regular season runs 18 weeks, so one re-upload is
unavoidable and two is comfortable.

| Upload | Expires | Covers |
|---|---|---|
| Week 1 (mid-Sep) | mid-Dec | Weeks 1–14 |
| Week 8 (early Nov) | early Feb | Weeks 8–18 and the playoffs |

The plan: **re-upload in week 8**, whether or not anything changed.
Steps, ten minutes: bump `CURRENT_PROJECT_VERSION` in `ios/project.yml`
→ `./ios/generate.sh` → open Xcode → §5 (archive, upload) → wait for
*Ready to Test* → the **Owner** group gets it automatically; add it to the
**League** group (TestFlight → League → Builds → **+**) → *What to Test*:
"Same app, new 90-day build. Nothing else changes." Same version number,
so it normally goes out without another Beta App Review. Testers see an
**Update** button in TestFlight and, if they ignore it, keep the old build
until its own day 90 — so upload the new one at least two weeks before the
old one dies, and mention it in the group chat once.

Set two calendar reminders now: **day 60** after the first upload
("upload the mid-season build") and **day 80** ("chase anyone who has not
updated"). The Xcode-installed copy on your own phone is separate and does
not expire.

## 10. What testers see, and what you will be asked

- Install **TestFlight** (free, App Store), then open your link. The
  first time, TestFlight explains beta software and asks them to
  **Accept**. The app installs from TestFlight, not the App Store.
- First launch of the app: they paste their own **private link** from
  your onboarding email. It goes into the phone's Keychain and nowhere
  else. Then the notifications permission dialog — they must tap
  **Allow** for the ruled-out alert to exist at all.
- "It says the build has expired." §9 — they need to tap **Update** in
  TestFlight, or the new build has not been added to the League group.
- "I never got the alert." In order: were notifications allowed
  (Settings → Notifications → Graded Takes)? Is Time Sensitive on in the
  same screen? Is the phone's token in your server's table (a reinstall
  changes it)? Did the server send to `api.push.apple.com` (TestFlight is
  production) and get `200`?
- Feedback: in the TestFlight app they can tap **Send Beta Feedback**,
  or take a screenshot in the app and choose *Share Beta Feedback*. It
  arrives under **TestFlight → Feedback** in App Store Connect, with the
  device model and iOS version attached.

When the season proves it out, the App Store proper is `docs/APPSTORE.md`
§9 — the same build, plus screenshots, the privacy nutrition label, the
age rating and the review notes.
