"""
check_ahri_directory.py

For each AHRI number in ahri_numbers_seen.json, queries the AHRI
Certification Directory's internal search API to check whether it's still
listed, and if so, produces a direct link to its detail page.

This does NOT scrape brand/model automatically — the directory's full
certificate-detail endpoint (GetCertificateDetails) requires a payload this
script hasn't cracked (returns HTTP 500 on the shapes tried so far; it's an
undocumented internal API). What this DOES automate reliably is the
existence check + a direct deep link, via GetQuickSearchByReferenceId,
which was confirmed working against the live API. Open each link in a
browser and read brand/model off the rendered page.

Some numbers will come back "not found" — per the AHRI directory, that
genuinely means the certification has been delisted/expired, not a script
failure (confirmed: this endpoint returns a clean empty array for unlisted
numbers, not an error).

INPUT:  ahri_numbers_seen.json (see Python/list_ahri_numbers.py)
OUTPUT: ahri_directory_check.csv — ahri_number, found, program_name,
        rating_condition, detail_url (one row per match; one "NOT FOUND"
        row for numbers with no match)
"""

import csv
import json
import time
import urllib.request

API_URL = "https://beta-ahrisearch.ahridirectory.org/SearchConfiguration/GetQuickSearchByReferenceId"
DETAIL_URL_TMPL = "https://www.ahridirectory.org/details/{program_id}/{reference_id}"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.ahridirectory.org",
    "Referer": "https://www.ahridirectory.org/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
DELAY_SECONDS = 1.0  # be polite — this is an undocumented internal API, not a public one


def query(reference_id):
    body = json.dumps({"ReferenceId": reference_id}).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8").strip()
    # A genuinely-unlisted number sometimes comes back as HTTP 200 with an
    # empty body rather than "[]" — both mean "no match", not an error.
    return json.loads(raw) if raw else []


def main():
    with open("ahri_numbers_seen.json", encoding="utf-8") as f:
        numbers = [x["number"] for x in json.load(f)["ahri_numbers"]]

    rows = []
    for i, number in enumerate(numbers, 1):
        try:
            matches = query(number)
        except Exception as e:
            print(f"  [{i}/{len(numbers)}] {number}: ERROR ({e})")
            rows.append({"ahri_number": number, "found": "error", "program_name": "",
                         "rating_condition": "", "detail_url": ""})
            time.sleep(DELAY_SECONDS)
            continue

        if not matches:
            print(f"  [{i}/{len(numbers)}] {number}: not found (delisted/expired)")
            rows.append({"ahri_number": number, "found": "no", "program_name": "",
                         "rating_condition": "", "detail_url": ""})
        else:
            for m in matches:
                url = DETAIL_URL_TMPL.format(program_id=m["ProgramId"], reference_id=m["ReferenceId"])
                print(f"  [{i}/{len(numbers)}] {number}: found — {m.get('ProgramName')}")
                rows.append({"ahri_number": number, "found": "yes", "program_name": m.get("ProgramName", ""),
                             "rating_condition": m.get("RatingCondition", ""), "detail_url": url})
        time.sleep(DELAY_SECONDS)

    with open("ahri_directory_check.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ahri_number", "found", "program_name", "rating_condition", "detail_url"])
        w.writeheader()
        w.writerows(rows)

    n_found = sum(1 for r in rows if r["found"] == "yes")
    print(f"\nwrote ahri_directory_check.csv — {n_found} listed matches across {len(numbers)} numbers checked")


if __name__ == "__main__":
    main()
