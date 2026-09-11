# GRADED TAKES for iPhone — how to open, run and rebuild it

This folder is the native iPhone app: a SwiftUI shell that shows your
published pages, plus the three things a website cannot do — a Time
Sensitive push when a starter is ruled out, the last week available
offline, and a home-screen widget. Read this once, top to bottom; after
that you will only ever need the two commands in the box.

```
./ios/generate.sh                     # rebuild the Xcode project from ios/project.yml
open ios/GradedTakes.xcodeproj        # open it in Xcode
```

What is where:

| Path | What it is | Who edits it |
|---|---|---|
| `ios/project.yml` | The project definition. Bundle ids, iOS 17 minimum, Swift 6, Info.plist keys, the Team ID. | You, once (Team ID) |
| `ios/GradedTakes/*.swift` | The app's Swift code | The Swift side |
| `ios/GradedTakesWidget/*.swift` | The widget's Swift code | The Swift side |
| `ios/Shared/*.swift` (optional) | Code compiled into both | The Swift side |
| `ios/GradedTakes/Assets.xcassets` | App icon (1024 px, from `design/icon.svg`), colours Navy / Gold / Paper / AccentColor | Nobody by hand — `ios/tools/make_icon.sh` |
| `ios/GradedTakesWidget/Assets.xcassets` | Same colours plus WidgetBackground | Same |
| `ios/GradedTakes/GradedTakes.entitlements` | Push, Time Sensitive, App Group | Xcode's "+ Capability" button, or nobody |
| `ios/GradedTakesWidget/GradedTakesWidget.entitlements` | App Group | Same |
| `ios/*/PrivacyInfo.xcprivacy` | The privacy manifest Apple requires (no tracking, nothing collected) | Nobody |
| `ios/GradedTakes.xcodeproj`, `ios/*/Info.plist` | **Generated.** Rewritten by `generate.sh`, not committed to git. | Nobody |
| `tools/xcodegen/` | The generator binary (XcodeGen 2.46.0). `tools/xcodegen/get.sh` re-downloads it. | Nobody |

Distribution to the league is TestFlight — that is a separate document,
`docs/TESTFLIGHT.md`. Do this one first.

---

## 1. Install Xcode (once, about an hour)

> Already done on this Mac: **Xcode 26.6 (17F113)** is in /Applications,
> its licence is agreed and the iOS simulator is installed. Open Xcode
> once, then pick up at step 4 (signing in).

1. Open the **App Store** app on the Mac, search **Xcode**, click **Get**
   then **Install**. It is about 3 GB down and 12 GB installed. (The
   Xcode 27 Release Candidate from developer.apple.com/download also works
   and is what Apple recommends this week; either is fine for this app.)
2. Open **Xcode** from Applications. Click **Agree** on the licence. When it
   asks which platforms to install, tick **iOS** and click **Download &
   Install**. Wait for it to finish — this is the iPhone simulator.
3. Optional but tidy — in **Terminal**, run this once so command-line tools
   point at the full Xcode rather than the small Command Line Tools package:
   ```
   sudo xcode-select -s /Applications/Xcode.app
   ```
   (It asks for your Mac password. Nothing else changes.)
4. Sign Xcode into your Apple Developer account: Xcode menu → **Settings…**
   (⌘,) → **Accounts** tab → **+** in the bottom-left → **Apple ID** →
   **Continue** → sign in with the Apple ID your Developer Program
   membership is on. Your name appears with the team listed underneath.
   Leave that window open for the next step.

## 2. Put your Team ID in `project.yml` (once)

Your **Team ID** is ten characters, letters and digits, like `AB12CD34EF`.
Two places to read it:

- In the Accounts window you just opened: click your Apple ID on the left,
  then look at the team row on the right — the ID is in grey next to your
  name (or click the team and it is shown in the detail pane).
- Or on the web: <https://developer.apple.com/account> → scroll to
  **Membership details** → **Team ID**.

Then:

1. Open `ios/project.yml` in any text editor (TextEdit is fine: right-click
   the file → Open With → TextEdit).
2. Find the line
   ```
       DEVELOPMENT_TEAM: ""        # <-- your 10-character Team ID goes between the quotes
   ```
   and put the ID between the quotes: `DEVELOPMENT_TEAM: "AB12CD34EF"`.
3. Save. In Terminal, from the project folder:
   ```
   ./ios/generate.sh
   ```
   It prints `Created project at …/ios/GradedTakes.xcodeproj`.

This is the only edit the project needs from you. (You can also pick the
team from a dropdown in Xcode — step 3 shows where — but Xcode writes that
into the generated project file, and the next `generate.sh` throws it away.
The yml is the one that sticks.)

## 3. Open the project and check signing

Double-click `ios/GradedTakes.xcodeproj` in Finder, or run
`open ios/GradedTakes.xcodeproj`.

Xcode opens with the file list on the left. Check signing once:

1. Click the blue **GradedTakes** icon at the very top of the left-hand
   file list. The middle of the window becomes the project editor.
2. In the editor's left column, under **TARGETS**, click **GradedTakes**.
3. Click the **Signing & Capabilities** tab across the top.
4. **Automatically manage signing** should be ticked and **Team** should
   show your name. If Team says *None*, choose yourself from the dropdown
   for now — and put the Team ID into `project.yml` afterwards so it
   survives regeneration.
5. Below that you will see three capability blocks that came from the
   entitlements file: **App Groups** (`group.com.gradedtakes.app`),
   **Push Notifications**, and **Time Sensitive Notifications**. Xcode
   registers all three with Apple the first time it signs. If it shows a
   red message like *"Provisioning profile doesn't include the … entitlement"*,
   see Troubleshooting at the end.
6. Under **TARGETS**, click **GradedTakesWidget** and repeat: Team set,
   App Groups present.

The first time, Xcode may take a minute and show "Registering bundle
identifier…" and "Creating provisioning profile…". That is normal.

## 4. Run it on the simulator

1. At the top of the Xcode window there is a scheme picker that reads
   **GradedTakes** and, next to it, a destination such as **iPhone 17 Pro**
   (or *Any iOS Device*). Click the destination and choose any iPhone
   under **iOS Simulators**.
   - If the list is empty: Xcode → **Settings…** → **Components** → under
     *Simulator*, click **Get** next to the newest iOS. Wait, then try again.
2. Press **⌘R** (or the ▶ button top-left). The simulator window appears,
   the app installs and launches. First build takes a minute or two.
3. To stop: **⌘.** (or the ■ button).

The simulator cannot receive real pushes from Apple's servers, but you can
fake one to test the tap-through: with the app installed on a booted
simulator, save this as `test.apns` on the Desktop:

```json
{
  "Simulator Target Bundle": "com.gradedtakes.app",
  "aps": {
    "alert": { "title": "Starter ruled out", "body": "Your WR1 is OUT. Kickoff in 90 min." },
    "sound": "default",
    "interruption-level": "time-sensitive"
  },
  "path": "home.html"
}
```

then drag the file onto the simulator window (or in Terminal:
`xcrun simctl push booted ~/Desktop/test.apns`). The widget also works on
the simulator: long-press the home screen → **+** (top-left) → search
**Graded Takes**.

## 5. Run it on your own iPhone

Needed once per phone.

1. **Cable.** Plug the iPhone into the Mac. On the phone, a **Trust This
   Computer?** dialog appears → **Trust** → enter the passcode.
2. **Developer Mode on the phone.** iPhone **Settings → Privacy & Security
   → scroll to the very bottom → Developer Mode** → turn it on → **Restart**.
   After the restart, unlock, tap **Turn On** on the prompt, enter the
   passcode. (If *Developer Mode* is not listed, connect the phone to Xcode
   first — it appears after Xcode has seen the device once.)
3. In Xcode, click the destination picker (where it said *iPhone 17 Pro*)
   and pick your phone under **iOS Devices**. The first time, Xcode says
   "Preparing device…" and copies developer files across; give it a few
   minutes.
4. Press **⌘R**. The app installs.
5. **Trust the developer certificate on the phone.** The first launch is
   blocked with *"Untrusted Developer"*. On the iPhone: **Settings →
   General → VPN & Device Management → Developer App → Apple Development:
   (your email) → Trust → Trust**. Then tap the Graded Takes icon on the
   home screen (or ⌘R again).
6. Xcode's console at the bottom of the window (View → Debug Area → Show
   Debug Area, or **⇧⌘Y**) shows the app's log while it runs from Xcode.
   The first launch asks to allow notifications; say **Allow**, and the
   app registers with Apple and hands the **device token** to the Graded
   Takes server. You need that token for the test push in
   `docs/TESTFLIGHT.md` — read it in the app under **Settings →
   Notifications → Device token** (64 hex characters; long-press to copy),
   or from the server's registration table.

Real pushes reach a phone, not the simulator. A build installed by Xcode
talks to Apple's **sandbox** push server; a TestFlight build talks to the
**production** one — the test-push script has a flag for each.

To go wireless after the first cable session: Xcode → **Window → Devices
and Simulators** → select the phone → tick **Connect via network**.

Because your membership is paid, a build installed this way keeps working
for a year (the free tier's seven-day limit does not apply).

## 6. Regenerating the project

Run `./ios/generate.sh` whenever:

- you edited `ios/project.yml` (Team ID, version numbers, an Info.plist key);
- Swift files were added or removed under `ios/GradedTakes/`,
  `ios/GradedTakesWidget/` or `ios/Shared/` and Xcode does not show them
  (the generator picks up every `.swift` file in those folders automatically);
- Xcode shows red (missing) files after a `git pull`.

Close Xcode first (⌘Q) to avoid it reloading half-way, run the script,
reopen the project. What survives regeneration: everything that is a real
file — Swift, the two `.entitlements`, both asset catalogs, the privacy
manifests. What does not: build settings changed in Xcode's UI, the Team
picked from Xcode's dropdown, files added through Xcode's *Add Files*
dialog (put them in the folder instead). Adding a capability with Xcode's
**+ Capability** button *does* survive, because Xcode writes it into the
entitlements file on disk.

Check the project without opening Xcode at all:

```
python3 ios/tools/check_project.py
```

It lists every file the project references, flags any that do not exist on
disk, and confirms the widget is embedded, the entitlements are wired, and
the app is iPhone-only. `RESULT: OK` at the end is what you want.

## 7. Version numbers (for every TestFlight upload)

In `project.yml`:

```
    MARKETING_VERSION: "1.0"      # what people see: 1.0, 1.1, 2.0
    CURRENT_PROJECT_VERSION: 1    # the build number: must go UP for every upload
```

Each upload to App Store Connect needs a build number higher than the last
one for that version. Bump `CURRENT_PROJECT_VERSION` (1 → 2 → 3 …), run
`generate.sh`, archive. Both targets read these two numbers from the
project level, so they never disagree (App Store Connect rejects a
mismatch).

## 8. Rebuilding the icon

If `design/icon.svg` changes:

```
ios/tools/make_icon.sh
```

It rasterises the SVG at 1024×1024 with `sips`, strips the alpha channel
(App Store Connect rejects an icon that has one), and writes it into the
asset catalog. Xcode derives every other icon size from that one file.
Rebuilding today produces a byte-identical file, so run it freely.

## Troubleshooting

**"Signing for GradedTakes requires a development team."** Step 2 (Team ID
in `project.yml`, then `generate.sh`), or pick the team in Signing &
Capabilities.

**"Failed to register bundle identifier"** or **"The app identifier
'com.gradedtakes.app' cannot be registered to your development team
because it is not available."** Someone else owns that bundle id on the
App Store. Register the App ID by hand first (`docs/TESTFLIGHT.md`, step 1)
— if Apple refuses it there too, the id is genuinely taken and both
`PRODUCT_BUNDLE_IDENTIFIER` lines in `project.yml` need a new value (and
the Swift side must be told, since the widget kind and app group derive
from it).

**"Provisioning profile … doesn't include the
com.apple.developer.usernotifications.time-sensitive entitlement"** (or the
App Groups / aps-environment one). Xcode's automatic signing did not tick
the capability on the App ID. Go to
<https://developer.apple.com/account/resources/identifiers/list> →
click **com.gradedtakes.app** → tick **Push Notifications**, **Time
Sensitive Notifications** and **App Groups** (Configure → select
`group.com.gradedtakes.app`) → **Save**. Back in Xcode: Settings → Accounts
→ select your Apple ID → **Download Manual Profiles**, then build again.

**"Unable to install … the device is locked"** — unlock the phone.

**Simulator shows a white screen or old pages** — that is the Swift
side's cache; long-press the app icon in the simulator → Remove App, then
⌘R.

**Xcode says the project needs "updating to recommended settings"** —
click **Don't Update**; those changes would be lost at the next
`generate.sh` anyway, and none are required.

**`python3` (or `swift`, `git`) prints "You have not agreed to the Xcode
license agreements".** Xcode is installed but has not been opened. Open
Xcode once and click **Agree** — or in Terminal, `sudo xcodebuild -license
accept`. Every command-line tool routes through Xcode once it is installed,
which is why an unrelated tool shows the message.

**"Command CodeSign failed"** on a simulator build — Xcode → Settings →
Accounts → your Apple ID → **Download Manual Profiles**; failing that,
quit Xcode, delete `~/Library/Developer/Xcode/DerivedData`, reopen.
