# build_tmy_temps.py
# Writes the browser-facing data/processed/tmy_temps.json — {City: [8760
# hourly dry-bulb temps, 0.1 C]} — from data/interim/tmy_hourly.csv
# (fetch_tmy.py output). This is the "typical year" series heatpump.html drives
# the engine with by default. Rows are already in chronological (Month, Day,
# Hour) order per city in tmy_hourly.csv.
#
# pip install pandas

import os
import json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
IN_CSV = os.path.join(HERE, "..", "data", "interim", "tmy_hourly.csv")
OUT_JSON = os.path.join(HERE, "..", "data", "processed", "tmy_temps.json")


def main():
    df = pd.read_csv(IN_CSV)
    df = df.sort_values(["City", "Month", "Day", "Hour"])
    out = {}
    for city, sub in df.groupby("City", sort=False):
        out[city] = [round(float(t), 1) for t in sub["Temperature_C"].to_numpy()]
        assert len(out[city]) in (8760, 8784), f"{city}: {len(out[city])} hours"
    # preserve a stable, human-friendly city order
    order = ["Ottawa", "Toronto", "Montreal", "Calgary", "Edmonton",
             "Vancouver", "Winnipeg", "Quebec City", "Halifax",
             "Saskatoon", "Regina", "Hamilton", "London", "Windsor"]
    ordered = {c: out[c] for c in order if c in out}
    for c in out:  # any city not in the explicit order list
        ordered.setdefault(c, out[c])

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(ordered, fh, separators=(",", ":"))
    print(f"[ok] {len(ordered)} cities -> {OUT_JSON}")
    for c, v in ordered.items():
        print(f"   {c:12s} {len(v)} h, mean {sum(v)/len(v):.1f} C, min {min(v):.1f} C")


if __name__ == "__main__":
    main()
