"""./yahoo.sh - connect one Yahoo app to as many people as want it.

    ./yahoo.sh status
    ./yahoo.sh authorize --person sam        print the link to send them
    ./yahoo.sh finish    --person sam --code XXXX
    ./yahoo.sh leagues   --person sam
    ./yahoo.sh import    --person sam --league 428472
    ./yahoo.sh check     --person sam        prove the token still refreshes
    ./yahoo.sh forget    --person sam        delete their token locally
    ./yahoo.sh purge                         drop artifacts past 24h retention

The owner runs all of these. The person on the other end only ever opens a
link, presses Allow, and sends back a short code - no developer portal, no
password, no cookie. docs/CONNECT_YAHOO.md is the note to send them.

Every line printed here goes through engine.yahoo.log, which redacts the app
secret and every token before anything reaches the terminal.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import yahoo                                      # noqa: E402

log = yahoo.log


def _only_person():
    """If exactly one person is connected, commands may omit --person."""
    people = yahoo.connected_people()
    return people[0]["person"] if len(people) == 1 else None


def _need_person(args) -> str:
    if args.person:
        return yahoo.clean_person(args.person)
    only = _only_person()
    if only:
        return only
    raise yahoo.YahooError(
        "Say who: --person <name>. It is just a label for the token file "
        "(e.g. 'sam'), not their Yahoo id.")


# --- commands ---------------------------------------------------------------

def cmd_status(args) -> int:
    st = yahoo.status()
    log("\n  YAHOO CONNECTION")
    log("   app     : %s" % st["detail"])
    if st.get("app_registered"):
        log("   redirect: %s" % st.get("redirect_uri"))
        log("   scope   : %s  (read-only; this tool never requests %s)"
            % (st.get("scope"), yahoo.SCOPE_WRITE))
    for person in st.get("people") or []:
        log("   person  : %-14s token mode %s, access token expires in %ss"
            % (person["person"], person["mode"], person["expires_in"]))
    stale = st.get("expired_artifacts") or []
    if stale:
        log("   NOTE    : %d artifact(s) past the 24h Yahoo retention window "
            "- run ./yahoo.sh purge or re-import" % len(stale))
    return 0 if st.get("app_registered") else 1


def cmd_authorize(args) -> int:
    person = yahoo.clean_person(args.person) if args.person else None
    if not person:
        log("  authorize needs --person <name> (a label for you, e.g. 'sam').")
        return 2
    app = yahoo.load_app()
    url, _state = yahoo.authorize_url(person, app=app)
    log("\n  SEND THIS TO %s" % person.upper())
    log("  " + "-" * 62)
    log(url)
    log("  " + "-" * 62)
    log("\n  What they will see: Yahoo's own consent screen, naming your app")
    log("  and asking to allow READ access to their Fantasy Sports data.")
    if app.redirect_uri == yahoo.OOB:
        log("  After they press Allow, Yahoo shows a short code on screen.")
        log("  They send you that code. Nothing else. No password, no cookie.")
    else:
        log("  After they press Allow, Yahoo sends them to %s, where nothing"
            % app.redirect_uri)
        log("  is listening - the page will fail to load. That is expected:")
        log("  the code is in the address bar. They copy the whole address.")
    log("\n  Then run:  ./yahoo.sh finish --person %s --code <what they sent>"
        % person)
    log("  docs/CONNECT_YAHOO.md is the note you can paste to them as-is.")
    return 0


def cmd_finish(args) -> int:
    person = _need_person(args)
    token = yahoo.exchange_code(person, args.code)
    log("\n  %s is connected." % person)
    log("   token file : %s  (mode 0600, never printed, never published)"
        % yahoo._rel(yahoo.token_path(person)))
    log("   scope      : %s (read-only)" % token.scope)
    log("   access tok : expires in %d minutes; refreshes itself"
        % int(token.seconds_left() // 60))
    log("   they can revoke this at any time in their Yahoo account -")
    log("   Account Info -> Recent activity -> Apps connected to your account")
    log("\n  Next: ./yahoo.sh leagues --person %s" % person)
    return 0


def cmd_leagues(args) -> int:
    person = _need_person(args)
    leagues = yahoo.list_leagues(person)
    if not leagues:
        log("\n  No current-season NFL leagues on that Yahoo account. If their")
        log("  league is from an earlier season, Yahoo needs the numeric game")
        log("  key for that year - tell me and I will add the flag.")
        return 1
    log("\n  LEAGUES %s CAN SEE (%d)" % (person, len(leagues)))
    for lg in leagues:
        log("   %-10s %-34s %2d teams  %s"
            % (lg["league_id"], lg["name"][:34], lg["teams"],
               lg["scoring_type"] or ""))
    log("\n  Import one: ./yahoo.sh import --person %s --league %s"
        % (person, leagues[0]["league_id"]))
    return 0


def cmd_import(args) -> int:
    person = _need_person(args)
    log("\n  Importing Yahoo league %s for %s..." % (args.league, person))
    summary = yahoo.import_league(person, args.league,
                                  rebuild=not args.no_rebuild)
    log("\n  CREATED")
    log("   league  : %s" % yahoo._rel(summary["league_file"]))
    log("   roster  : %s  (%d players)"
        % (yahoo._rel(summary["roster_file"]), summary["my_roster_size"]))
    log("   rankings: %s" % yahoo._rel(summary["rankings_csv"]))
    rb = summary.get("rebuild")
    if rb:
        line = ("   rebuild : %d seeded, %d projections filled (%s)"
                % (rb["seeded"], rb["filled"], rb["scoring"]))
        if rb.get("tiered") is not None:
            line += ", %d Chen tier rows" % rb["tiered"]
        log(line)
    log("   settings: %d teams, reception=%s, waivers=%s, %d roster spots"
        % (summary["teams"], summary["reception"], summary["waiver_mode"],
           len(summary["roster_spots"])))
    if summary["superflex"]:
        log("   NOTE    : SUPERFLEX league - rankings seeded from 1-QB ADP "
            "will undervalue QBs")
    if summary["unmapped_scoring"]:
        log("   NOTE    : %d Yahoo scoring rule(s) have no engine name and "
            "were carried verbatim under scoring.unmapped: %s"
            % (len(summary["unmapped_scoring"]),
               ", ".join(summary["unmapped_scoring"])))
    for path in summary.get("purged") or []:
        log("   PURGED  : %s  (past 24h retention, dropped by this import)"
            % yahoo._rel(path))
    log("   EXPIRES : %s  (Yahoo APIs Terms of Use s2.1, 24h retention) -"
        % summary["expires_at"])
    log("             re-run this import to refresh, ./yahoo.sh purge to drop")
    log("   NEXT    : set my_slot in %s once the draft order is known"
        % yahoo._rel(summary["league_file"]))
    return 0


def cmd_check(args) -> int:
    person = _need_person(args)
    log("\n  Checking %s's Yahoo connection (read-only)..." % person)
    before = yahoo.load_token(person)
    token = yahoo.refresh_token(person)
    log("   refresh    : ok - new access token, expires in %d minutes"
        % int(token.seconds_left() // 60))
    log("   token file : %s (mode %s)"
        % (yahoo._rel(yahoo.token_path(person)),
           oct(os.stat(yahoo.token_path(person)).st_mode & 0o777)))
    log("   scope      : %s (read-only)" % token.scope)
    log("   rotated    : %s" % ("yes"
                                if token.refresh_token != before.refresh_token
                                else "no - Yahoo kept the same refresh token"))
    leagues = yahoo.list_leagues(person)
    log("   leagues    : %d visible" % len(leagues))
    for lg in leagues:
        log("                %s  %s" % (lg["league_id"], lg["name"]))
    log("\n  Connection works. Nothing was modified - this tool is read-only.")
    return 0


def cmd_forget(args) -> int:
    person = _need_person(args)
    removed = yahoo.forget_person(person)
    if not removed:
        log("\n  Nothing stored for %s." % person)
        return 0
    for path in removed:
        log("  deleted %s" % yahoo._rel(path))
    log("\n  That removes OUR copy. To cut the grant off at Yahoo's end too,")
    log("  they should go to Yahoo Account Info -> Recent activity -> Apps")
    log("  connected to your account, and remove this app. Tell them to.")
    return 0


def cmd_purge(args) -> int:
    removed = yahoo.purge_expired()
    if not removed:
        log("\n  Nothing past the 24-hour Yahoo retention window.")
        return 0
    for path in removed:
        log("  removed %s (past 24h retention)" % yahoo._rel(path))
    log("\n  Re-run ./yahoo.sh import to pull fresh copies.")
    return 0


COMMANDS = {"status": cmd_status, "authorize": cmd_authorize,
            "finish": cmd_finish, "leagues": cmd_leagues,
            "import": cmd_import, "check": cmd_check,
            "forget": cmd_forget, "purge": cmd_purge}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="./yahoo.sh",
        description="Yahoo Fantasy: one registered app, many people, "
                    "read-only.")
    parser.add_argument("command", nargs="?", default="status",
                        choices=sorted(COMMANDS))
    parser.add_argument("--person", help="label for whose token to use")
    parser.add_argument("--code", help="the code (or redirect URL) they sent "
                                       "back after consenting")
    parser.add_argument("--league", help="Yahoo league id or full league_key")
    parser.add_argument("--no-rebuild", action="store_true",
                        help="skip the rankings rebuild (offline)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(
        sys.argv[1:] if argv is None else list(argv))
    if args.command == "finish" and not args.code:
        log("  finish needs --code <what they sent back>.")
        return 2
    if args.command == "import" and not args.league:
        log("  import needs --league <id>. List them with ./yahoo.sh leagues.")
        return 2
    try:
        return COMMANDS[args.command](args)
    except yahoo.YahooError as exc:
        # Already redacted by YahooError.__init__; log() redacts again anyway.
        log("\n  %s: %s" % (type(exc).__name__, exc))
        return 1
    except KeyboardInterrupt:
        log("")
        return 1


if __name__ == "__main__":
    sys.exit(main())
