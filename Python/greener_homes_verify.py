"""
greener_homes_verify.py

Publishes the curated NRCan Greener Homes figures to
construction_json/programs.json, and verifies they still match the live
progress-update page before doing so.

WHY THIS IS A VERIFIER, NOT A SCRAPER
    NRCan's progress page has no data file and no <table> elements. Its
    provincial figures sit in a run of icon blocks where each province's NAME
    appears AFTER its numbers in document order. A positional parser therefore
    pairs them off by one and silently mis-assigns every province — which is
    exactly the failure that produces a confidently wrong chart. (Confirmed by
    hand against the February 2026 page on 2026-08-27: reading name-then-number
    yields Ontario = 26,002, which is really Nova Scotia's count.)

    So the numbers are transcribed by hand into greener_homes_data.json, which
    lives on `main` as part of the decision record, and this script's job is to
    prove they have not gone stale: it fetches the live page and asserts every
    string in `verify_strings` still appears in it verbatim. That check cannot
    mis-assign a province, and it fails loudly when NRCan publishes an update.

    When it fails, the fix is to read the page, update
    greener_homes_data.json (including as_of and source_url), and re-run.

USAGE
    python greener_homes_verify.py            # verify, then publish
    python greener_homes_verify.py --skip-check   # publish without fetching
Exits non-zero if the live page no longer carries the transcribed figures, so
the scheduled refresh does not quietly publish stale numbers.
"""

import re
import sys
import json
import html
import argparse
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = Path(__file__).resolve().parent / "greener_homes_data.json"
OUT_FILE = REPO_ROOT / "construction_json" / "programs.json"

HEADERS = {"User-Agent": "OttawaVisuals-EnergySuite/1.0 (construction tracker)"}


def page_text(url):
    """Fetch the progress page and flatten it to plain text with the numeric
    formatting intact, so 'verify_strings' can be matched verbatim."""
    r = requests.get(url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    body = re.sub(r"<script.*?</script>", " ", r.text, flags=re.S | re.I)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    # collapse the whitespace NRCan sprinkles inside "$ 748.2 million"
    return re.sub(r"\s+", " ", body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-check", action="store_true",
                    help="publish without fetching the live page")
    args = ap.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    wanted = data["verify_strings"]

    if args.skip_check:
        print("!! --skip-check: publishing WITHOUT verifying against the live page")
    else:
        print(f"checking {len(wanted)} transcribed figures against")
        print(f"  {data['source_url']}")
        try:
            text = page_text(data["source_url"])
        except Exception as e:
            print(f"\n!! could not fetch the progress page: {e}", file=sys.stderr)
            sys.exit(1)

        missing = [w for w in wanted if w not in text]
        if missing:
            print(f"\n!! {len(missing)} of {len(wanted)} figures are NO LONGER on the "
                  f"live page:", file=sys.stderr)
            for m in missing:
                print(f"     {m}", file=sys.stderr)
            print("\n   NRCan has most likely published a newer progress update.",
                  file=sys.stderr)
            print("   Read the page, update Python/greener_homes_data.json "
                  "(figures, as_of, source_url), then re-run.", file=sys.stderr)
            print("   Do NOT publish until the transcription matches — the page "
                  "labels these figures with an as-of date.", file=sys.stderr)
            sys.exit(1)
        print(f"  all {len(wanted)} figures still present — transcription is current")

    payload = {k: v for k, v in data.items()
               if k not in ("_comment", "verify_strings")}
    payload["verified"] = "not checked" if args.skip_check else "live page matched"
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT_FILE.relative_to(REPO_ROOT)} "
          f"({OUT_FILE.stat().st_size/1024:.1f} KB, as of {data['as_of']})")


if __name__ == "__main__":
    main()
