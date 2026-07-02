"""
AHRI Directory data extractor.

Re-queries the site's internal API (quick search + detail only, no PDF
download) for a list of confirmed AHRI numbers, and builds:
  - ahri_data_long.csv      one row per (ahri_number, field) - works for ANY category
  - ahri_data_by_category.xlsx   one sheet per category, pivoted wide

Usage:
    pip install requests pandas openpyxl
    python ahri_extract_data.py numbers.txt
"""

import sys
import csv
import time
from pathlib import Path
import requests
import pandas as pd

BASE = "https://beta-ahrisearch.ahridirectory.org/SearchConfiguration"
QUICK_SEARCH_URL = f"{BASE}/GetQuickSearchByReferenceId"
DETAIL_URL = f"{BASE}/GetSearchDetailResults"

DELAY_SECONDS = 1.0
LONG_CSV = Path("ahri_data_long.csv")
XLSX_OUT = Path("ahri_data_by_category.xlsx")

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.ahridirectory.org",
    "Referer": "https://www.ahridirectory.org/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def safe_json(r: requests.Response):
    if not r.text.strip():
        return None, f"empty_response(status={r.status_code})"
    try:
        return r.json(), None
    except ValueError:
        snippet = r.text[:150].replace("\n", " ")
        return None, f"non_json_response(status={r.status_code}, body_start={snippet!r})"


def fetch_one(session: requests.Session, ahri_number: str):
    """Returns (list_of_field_rows, status_note). status_note is None on success."""
    r = session.post(
        QUICK_SEARCH_URL, json={"ReferenceId": ahri_number}, headers=HEADERS, timeout=15
    )
    quick, err = safe_json(r)
    if err:
        return None, f"quicksearch_error: {err}"
    if not quick:
        return None, "not_found"

    program_id = quick[0].get("ProgramId")
    if program_id is None:
        return None, "no_program_id"

    r = session.post(
        DETAIL_URL,
        json={"ProgramId": str(program_id), "ReferenceId": ahri_number},
        headers=HEADERS,
        timeout=15,
    )
    details, err = safe_json(r)
    if err:
        return None, f"detail_error: {err}"
    if not details:
        return None, "details_empty"

    return details, None


def main(numbers_file: str):
    numbers = [
        line.strip()
        for line in Path(numbers_file).read_text().splitlines()
        if line.strip()
    ]

    long_rows = []
    fetch_log = []

    with requests.Session() as session:
        for i, num in enumerate(numbers, 1):
            print(f"[{i}/{len(numbers)}] {num}...", end=" ", flush=True)
            details, err = fetch_one(session, num)
            if err:
                print(err)
                fetch_log.append({"ahri_number": num, "status": err})
            else:
                print(f"ok ({len(details)} fields)")
                fetch_log.append({"ahri_number": num, "status": "ok"})
                for row in details:
                    long_rows.append({
                        "ahri_number": num,
                        "category": row.get("ProgramDescription"),
                        "group": row.get("GroupName"),
                        "field": row.get("UIUXDisplayName"),
                        "field_code": row.get("AzureUniqueName"),
                        "value": row.get("COLUMN_VALUE"),
                    })
            time.sleep(DELAY_SECONDS)

    # Long-format CSV (works regardless of category)
    with open(LONG_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["ahri_number", "category", "group", "field", "field_code", "value"]
        )
        writer.writeheader()
        writer.writerows(long_rows)

    # Fetch log
    fetch_log_path = Path("ahri_extract_log.csv")
    with open(fetch_log_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ahri_number", "status"])
        writer.writeheader()
        writer.writerows(fetch_log)

    # Pivot wide, one sheet per category
    if long_rows:
        df = pd.DataFrame(long_rows)
        with pd.ExcelWriter(XLSX_OUT, engine="openpyxl") as writer:
            for category, group_df in df.groupby("category"):
                wide = group_df.pivot_table(
                    index="ahri_number",
                    columns="field",
                    values="value",
                    aggfunc="first",
                )
                sheet_name = (category or "Unknown")[:31]  # Excel sheet name limit
                wide.to_excel(writer, sheet_name=sheet_name)

    ok_count = sum(1 for r in fetch_log if r["status"] == "ok")
    print(f"\nDone. {ok_count}/{len(numbers)} fetched successfully.")
    print(f"Long CSV: {LONG_CSV}")
    print(f"Workbook: {XLSX_OUT}")
    print(f"Fetch log: {fetch_log_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python ahri_extract_data.py numbers.txt")
        sys.exit(1)
    main(sys.argv[1])
