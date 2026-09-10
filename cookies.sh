#!/bin/bash
# Interactive ESPN cookie setup - prompts for the two values, writes the
# secrets file with correct formatting and permissions, then verifies.
cd "$(dirname "$0")"
echo "ESPN cookie setup for league 284298483 ('The Original 8')"
echo
echo "In Chrome DevTools: Application tab -> Cookies -> https://www.espn.com"
echo "Click the espn_s2 row, copy its Value. Then the SWID row, same."
echo
printf "Paste espn_s2 value: "
read -r S2
printf "Paste SWID value:    "
read -r SWID
.venv/bin/python - "$S2" "$SWID" <<'PY'
import json, os, sys
s2 = sys.argv[1].strip().strip('"').strip()
swid = sys.argv[2].strip().strip('"').strip()
if swid and not swid.startswith("{"):
    swid = "{" + swid.strip("{}") + "}"   # braces are required; add if lost in copy
if not s2 or not swid or len(s2) < 40:
    print("\n  espn_s2 looks too short or empty - re-copy the full Value cell and rerun ./cookies.sh")
    raise SystemExit(1)
path = "data/espn_secrets.json"
with open(path, "w") as fh:
    json.dump({"league_id": 284298483, "espn_s2": s2, "swid": swid}, fh)
os.chmod(path, 0o600)
print("\n  saved " + path + " (locked to your user)")
PY
[ $? -eq 0 ] && echo && echo "== verifying connection ==" && ./espn.sh check
