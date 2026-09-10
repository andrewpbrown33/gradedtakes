# ESPN setup — for the OWNER, only, for his own league

**This file is for you, not for your friends.** Everything below uses the
cookies of the ESPN account signed in on *this* Mac — your own. There is no
step in this file that a second person can do, because there is no honest way
for a second person to do it: it would mean sending you their cookies.

**Never ask anyone else for their `espn_s2` or `SWID`.** Those are whole
Disney/ESPN account credentials, not fantasy-scoped keys. Asking for them
breaks ESPN's terms for the person who sends them, they cannot be revoked
without a password change, and this project does not accept them from anybody
but the account sitting at this keyboard.

**To get somebody else's ESPN league in, send them
[`docs/CONNECT_ESPN.md`](docs/CONNECT_ESPN.md).** It has the two routes that
cost them no credential at all — making the league viewable to the public
(then we read it with no login, and it refreshes itself), or pasting their
roster text. Both produce the same pages as this file does. Neither one asks
them for a cookie. That doc, not this one, is the thing you forward.

---

## What this file is for

The owner's own league, on the owner's own Mac: live draft auto-ingest. It is
the fix for what happened in the Yahoo draft — manual typing captured 33 of
160 picks, then the board went stale. ESPN lets us read picks automatically,
so you never type a pick again.

Two minutes, all of it yours. Steps 1-3 use the ESPN login already in this
Mac's browser; nothing leaves the machine.

## 1. Find your league ID

Open your league in ESPN. The URL looks like:

    https://fantasy.espn.com/football/league?leagueId=1234567

That number is your league ID.

## 2. Get your two cookies

*Your own, from the browser on this Mac. If you are reading this step on
behalf of somebody else's league, stop — that is what
[`docs/CONNECT_ESPN.md`](docs/CONNECT_ESPN.md) is for.*

ESPN has no official API, so we authenticate the same way your browser does,
with two cookies it already has.

**In Chrome or Edge:**
1. Go to `fantasy.espn.com` and make sure you're logged in
2. Press `F12` (or Cmd+Option+I) to open DevTools
3. Click the **Application** tab
4. In the left sidebar: **Storage → Cookies → https://fantasy.espn.com**
5. Find two rows and copy their **Value** column:
   - `espn_s2`  (a very long string)
   - `SWID`     (looks like `{ABC12345-6789-...}` — keep the curly braces)

**In Safari:** enable Develop menu first (Settings → Advanced → "Show features
for web developers"), then Develop → Show Web Inspector → Storage → Cookies.

## 3. Put them in a file

Create `data/espn_secrets.json`:

```json
{
  "league_id": 1234567,
  "espn_s2": "PASTE_THE_LONG_STRING",
  "swid": "{PASTE-WITH-BRACES}"
}
```

**Keep this to yourself.** These cookies are live access to your ESPN account —
don't paste them into a chat (including to me), commit them, or share the file.
I never need the values; the code reads them off your own disk. The file is
gitignored and locked to your user account automatically.

**And it works in the other direction too: never accept anyone else's.** If a
friend offers to send their `espn_s2` and `SWID` to save time, say no and send
them [`docs/CONNECT_ESPN.md`](docs/CONNECT_ESPN.md) instead. There is no file
in this project that a second person's cookies belong in.

## 4. Test it

```bash
./espn.sh check
```

You should see your league name, team count, scoring, roster slots, and your
draft position. Run it tonight, well before the draft — not five minutes
before.

## During the draft

```bash
./espn.sh draft
```

It polls ESPN every few seconds, pulls new picks automatically, and prints your
recommendation block the moment you're on the clock. You type nothing.

Manual paste still works as a fallback if the connection drops mid-draft — the
same war room, the same commands.

## What can go wrong

**"Private league" / 401** — the cookies are wrong or expired. Re-copy them;
they change when you log out and back in.

**SWID without braces** — it needs the `{` and `}`. Easy to lose on copy.

**Draft hasn't started** — `refresh_draft` returns nothing until ESPN marks the
draft live. That's expected; `./espn.sh check` still works beforehand.
