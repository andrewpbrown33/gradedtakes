#!/usr/bin/env python3
"""Send ONE Time Sensitive test push to an iPhone running Graded Takes.

Standard-library Python driving two binaries every Mac already has:
  openssl  - signs the APNs auth token (ES256; not in the stdlib)
  curl     - speaks HTTP/2 to APNs (http.client is HTTP/1.1 only)

    python3 docs/send_test_push.py \\
        --key ~/secrets/AuthKey_ABC123DEFG.p8 \\
        --team-id AB12CD34EF \\
        --device-token 0123abcd...(64 hex characters, from the app:
                       Settings -> Notifications -> Device token)

    add  --production  for a TestFlight / App Store build (default: sandbox,
    which is what a build installed by Xcode uses). Wrong environment is the
    #1 cause of "400 BadDeviceToken".

Nothing is hardcoded: the key path, key id, team id and device token all come
from arguments (or the environment: APNS_KEY, APNS_KEY_ID, APNS_TEAM_ID).
The key id is read from the file name AuthKey_<KEYID>.p8 when --key-id is
omitted. The script never prints the key, the signed token, or anything but
the APNs response. See docs/TESTFLIGHT.md, "Send yourself a test push".
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time

DEFAULT_TOPIC = "com.gradedtakes.app"
HOSTS = {"sandbox": "api.sandbox.push.apple.com", "production": "api.push.apple.com"}
REASONS = {
    "BadDeviceToken": "the token is not valid for this environment - Xcode-installed builds "
                      "need sandbox (default), TestFlight/App Store builds need --production",
    "DeviceTokenNotForTopic": "this token belongs to a different bundle id than --topic",
    "TopicDisallowed": "the key is Topic Specific and does not cover this bundle id",
    "InvalidProviderToken": "APNs rejected the signed token - wrong --team-id, wrong key id, "
                            "or the .p8 is not the key that id refers to",
    "ExpiredProviderToken": "the Mac's clock is off; tokens older than an hour are refused",
    "MissingProviderToken": "no authorization header reached APNs (curl too old for --http2?)",
    "Unregistered": "the app was deleted from that phone - drop this token",
    "TooManyProviderTokenUpdates": "you generated a new token less than 20 minutes after the last "
                                   "one - wait, then retry",
    "PayloadTooLarge": "the payload is over 4 KB",
    "BadCollapseId": "apns-collapse-id must be 64 bytes or fewer",
}


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def der_to_raw(der: bytes) -> bytes:
    """ECDSA DER SEQUENCE{INTEGER r, INTEGER s} -> 64-byte r||s (RFC 7518 §3.4).
    APNs happens to accept DER too, but a strict JWT verifier does not."""
    if not der or der[0] != 0x30:
        raise ValueError("not a DER ECDSA signature")
    i = 2 + ((der[1] & 0x7F) if der[1] & 0x80 else 0)
    parts = []
    for _ in range(2):
        if der[i] != 0x02:
            raise ValueError("malformed DER signature")
        length = der[i + 1]
        parts.append(der[i + 2:i + 2 + length].lstrip(b"\x00").rjust(32, b"\x00"))
        i += 2 + length
    return parts[0] + parts[1]


def sign_jwt(key_path: str, key_id: str, team_id: str) -> str:
    header = b64url(json.dumps({"alg": "ES256", "kid": key_id}, separators=(",", ":")).encode())
    claims = b64url(json.dumps({"iss": team_id, "iat": int(time.time())}, separators=(",", ":")).encode())
    signing_input = ("%s.%s" % (header, claims)).encode("ascii")
    try:
        der = subprocess.run(
            ["openssl", "dgst", "-binary", "-sha256", "-sign", key_path],
            input=signing_input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
    except subprocess.CalledProcessError as err:
        sys.exit("openssl could not sign with %s: %s" % (key_path, err.stderr.decode(errors="replace").strip()))
    return "%s.%s.%s" % (header, claims, b64url(der_to_raw(der)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", default=os.environ.get("APNS_KEY"),
                    help="path to AuthKey_<KEYID>.p8 (env APNS_KEY)")
    ap.add_argument("--key-id", default=os.environ.get("APNS_KEY_ID"),
                    help="10-character Key ID; read from the file name when omitted (env APNS_KEY_ID)")
    ap.add_argument("--team-id", default=os.environ.get("APNS_TEAM_ID"),
                    help="10-character Team ID from Membership details (env APNS_TEAM_ID)")
    ap.add_argument("--device-token", required=True,
                    help="64 hex characters, shown in the app under Settings -> Notifications -> "
                         "Device token once Apple has answered")
    ap.add_argument("--production", action="store_true",
                    help="use api.push.apple.com (TestFlight / App Store builds). Default: sandbox")
    ap.add_argument("--topic", default=DEFAULT_TOPIC, help="bundle id (default %(default)s)")
    ap.add_argument("--title", default="Starter ruled out")
    ap.add_argument("--body", default="Your WR1 is OUT. Kickoff in 90 min. Open your lineup.")
    ap.add_argument("--path", default="home.html",
                    help="page the app opens when the alert is tapped, relative to the reader's "
                         "link (custom 'path' key, e.g. lineup-espn-1-week1.html)")
    ap.add_argument("--week", type=int, default=1, help="week number for the thread-id (default 1)")
    ap.add_argument("--needs", metavar="N",  type=int,
                    help="also update the widget: N calls need you (sends the optional 'needs' block)")
    ap.add_argument("--silent", action="store_true",
                    help="send the silent pre-fetch push instead of an alert (content-available, "
                         "priority 5; the app warms --path in the background, nothing is shown)")
    ap.add_argument("--collapse-id", default="ruled-out",
                    help="apns-collapse-id: a newer push with the same id replaces the older one")
    ap.add_argument("--expires-in", type=int, default=5400,
                    help="seconds APNs may hold the push for an offline phone (default 90 min - "
                         "after kickoff the alert is worthless)")
    args = ap.parse_args()

    if not args.key:
        sys.exit("--key (or APNS_KEY) is required: the path to your AuthKey_<KEYID>.p8")
    key_path = os.path.expanduser(args.key)
    if not os.path.isfile(key_path):
        sys.exit("no such key file: %s" % key_path)
    key_id = args.key_id
    if not key_id:
        m = re.match(r"AuthKey_([A-Z0-9]{10})\.p8$", os.path.basename(key_path))
        if not m:
            sys.exit("could not read the Key ID from the file name; pass --key-id")
        key_id = m.group(1)
    if not args.team_id or not re.fullmatch(r"[A-Z0-9]{10}", args.team_id):
        sys.exit("--team-id (or APNS_TEAM_ID) must be the 10-character Team ID")
    token = args.device_token.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        sys.exit("--device-token must be 64 hex characters (got %d)" % len(token))
    if len(args.collapse_id.encode()) > 64:
        sys.exit("--collapse-id must be 64 bytes or fewer")

    curl_version = subprocess.run(["curl", "--version"], stdout=subprocess.PIPE, text=True).stdout
    if "HTTP2" not in curl_version:
        sys.exit("this curl has no HTTP/2 support; APNs requires it (macOS 26's /usr/bin/curl has it)")

    env = "production" if args.production else "sandbox"
    host = HOSTS[env]
    now = int(time.time())
    jwt = sign_jwt(key_path, key_id, args.team_id)
    # Payload shape is the contract in ios/GradedTakes/Push/Push.swift.
    if args.silent:
        payload = {"aps": {"content-available": 1}, "path": args.path}
    else:
        payload = {
            "aps": {
                "alert": {"title": args.title, "body": args.body},
                "sound": "default",
                "interruption-level": "time-sensitive",
                "relevance-score": 1.0,
                "thread-id": "week-%d" % args.week,
                "badge": 1,
            },
            "path": args.path,
        }
        if args.needs is not None:
            payload["needs"] = {
                "count": args.needs,
                "headline": "%d call%s need%s you" % (args.needs, "" if args.needs == 1 else "s",
                                                      "s" if args.needs == 1 else ""),
                "week": args.week,
                "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "path": args.path,
            }
    body = json.dumps(payload, separators=(",", ":"))
    if len(body.encode()) > 4096:
        sys.exit("payload is %d bytes; APNs allows 4096" % len(body.encode()))

    print("APNs %s  %s  topic %s  device %s...%s  path %s"
          % (env, "silent pre-fetch" if args.silent else "time-sensitive alert",
             args.topic, token[:6], token[-6:], args.path))
    cmd = [
        "curl", "--silent", "--show-error", "--http2",
        "--max-time", "20",
        "--header", "authorization: bearer " + jwt,
        "--header", "apns-topic: " + args.topic,
        "--header", "apns-push-type: " + ("background" if args.silent else "alert"),
        "--header", "apns-priority: " + ("5" if args.silent else "10"),
        "--header", "apns-expiration: %d" % (now + args.expires_in),
        "--header", "content-type: application/json",
        "--data", body,
        "--write-out", "\n%{http_code} %{http_version}",
        "https://%s/3/device/%s" % (host, token),
    ]
    if not args.silent:
        cmd[-3:-3] = ["--header", "apns-collapse-id: " + args.collapse_id]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        sys.exit("curl failed (%d): %s" % (res.returncode, res.stderr.strip()))
    *resp_lines, status_line = res.stdout.split("\n")
    resp = "\n".join(resp_lines).strip()
    status, _, http_version = status_line.partition(" ")
    if status == "200":
        if args.silent:
            print("200 OK over HTTP/%s - APNs accepted the silent push. Nothing appears on the phone; "
                  "Apple delivers it when it decides to (a few per hour at most)." % http_version)
        else:
            print("200 OK over HTTP/%s - APNs accepted it. If it did not show on the phone within a few "
                  "seconds: is the app allowed to notify (Settings -> Notifications -> Graded Takes), "
                  "and is Time Sensitive on there?" % http_version)
        return 0
    reason = ""
    try:
        reason = json.loads(resp).get("reason", "")
    except ValueError:
        pass
    print("%s %s" % (status, resp or "(empty body)"))
    if reason in REASONS:
        print("-> " + REASONS[reason])
    elif status == "410":
        print("-> " + REASONS["Unregistered"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
