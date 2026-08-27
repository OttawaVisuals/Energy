"""
cited_figures_verify.py

Publishes the curated cite-only figures in cited_figures.json to
construction_json/programs.json, after checking each one still appears on its
live source page.

WHY THESE ARE VERIFIED, NOT SCRAPED
    Neither source publishes a data file. NRCan's Greener Homes progress page
    has no <table> elements at all, and its provincial figures sit in a run of
    icon blocks where each province's NAME appears AFTER its numbers in
    document order — a positional parser therefore pairs them off by one and
    silently mis-assigns every province, producing a confidently wrong chart.
    (Confirmed by hand on 2026-08-27: reading name-then-number gives Ontario =
    26,002, which is really Nova Scotia's count.)

    So the numbers are transcribed by hand into cited_figures.json, which lives
    on `main` as part of the decision record, and this script proves they have
    not gone stale: it fetches each source page and asserts every string in
    that source's `verify_strings` still appears verbatim. That check cannot
    mis-assign anything, and it fails loudly when a publisher posts an update.

    This is also the licence-safe shape for association data. These are cited
    published figures with attribution and an as-of date — not a republished
    dataset. CaGBC is deliberately absent: it publishes no running total and
    its project database is behind a sign-in, so there is nothing here that
    could be verified this way. Getting a CaGBC count means asking CaGBC.

    When a check fails, the fix is to read the page, update
    cited_figures.json (figures, as_of, source_url, verify_strings), re-run.

USAGE
    python cited_figures_verify.py               # verify, then publish
    python cited_figures_verify.py --skip-check  # publish without fetching
Exits non-zero if any source no longer carries its transcribed figures, so the
scheduled refresh never quietly publishes stale numbers.
"""

import re
import sys
import json
import html
import argparse
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = Path(__file__).resolve().parent / "cited_figures.json"
OUT_FILE = REPO_ROOT / "construction_json" / "programs.json"

# Some publishers refuse a bare script user-agent; this one identifies the
# project honestly rather than pretending to be a browser.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OttawaVisuals-EnergySuite/1.0; "
                         "construction tracker; +https://ottawavisuals.github.io/Energy)"}


def page_text(url):
    """Fetch a page and flatten it to plain text with numeric formatting
    intact, so verify_strings can be matched verbatim."""
    r = requests.get(url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    body = re.sub(r"<script.*?</script>", " ", r.text, flags=re.S | re.I)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    return re.sub(r"\s+", " ", body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-check", action="store_true",
                    help="publish without fetching the live pages")
    args = ap.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    sources = data["sources"]
    failures = []

    for key, src in sources.items():
        wanted = src.get("verify_strings", [])
        if args.skip_check:
            print(f"!! {key}: --skip-check, NOT verified")
            continue
        print(f"checking {key}: {len(wanted)} figures against {src['source_url']}")
        try:
            text = page_text(src["source_url"])
        except Exception as e:
            print(f"  !! could not fetch: {e}", file=sys.stderr)
            failures.append((key, ["<page could not be fetched>"]))
            continue
        missing = [w for w in wanted if w not in text]
        if missing:
            failures.append((key, missing))
            print(f"  !! {len(missing)} of {len(wanted)} figures no longer present",
                  file=sys.stderr)
        else:
            print(f"  all {len(wanted)} figures still present "
                  f"(as of {src['as_of']})")

    if failures:
        print("\n!! transcription is stale — NOT publishing:", file=sys.stderr)
        for key, missing in failures:
            print(f"   {key}: {', '.join(missing)}", file=sys.stderr)
        print("\n   The publisher has most likely posted an update. Read the "
              "page(s), update Python/cited_figures.json (figures, as_of, "
              "source_url, verify_strings), then re-run.", file=sys.stderr)
        sys.exit(1)

    payload = {"sources": {}}
    for key, src in sources.items():
        payload["sources"][key] = {k: v for k, v in src.items()
                                   if k != "verify_strings"}
    payload["verified"] = "not checked" if args.skip_check else "live pages matched"
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nwrote {OUT_FILE.relative_to(REPO_ROOT)} "
          f"({OUT_FILE.stat().st_size/1024:.1f} KB, {len(sources)} sources)")


if __name__ == "__main__":
    main()
