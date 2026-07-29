"""
Quick check: installed heat-pump capacity vs. home design heat loss (ERS).

WHY THIS EXISTS
----------------
The engine rebuild (2026-07-29, ROADMAP "engine rebuild") replaces auto-sizing
with a tier x capacity-band dropdown pair that the user picks directly. Before
writing UI copy/defaults around that dropdown, this is a quick sanity check on
real installs: how does the AHRI-certified installed capacity
(`Post_HPCapacity47`, kW at rated 47F -- see Python/join_hp_capacity.py, the
validated field, not the unreliable auditor-entered HPCAP which runs 1.55x
high) compare to the home's own design heat loss (`Post_HeatLoss`, kW,
EGHDESHTLOSS post-retrofit)? If real installs cluster near ratio 1.0, a
"default to ~100% of design load" suggestion is defensible; if they're
scattered, the page should not imply a typical ratio.

STATUS: standalone analysis, not gating the engine rebuild. Reads the same
ers_web_<PROV>.parquet files (Python/ers_web_pipeline.py + join_hp_capacity.py
outputs) the archetype pipeline already reads.

INPUT:  C:\\ERS\\web\\ers_web_<PROV>.parquet
OUTPUT: data/interim/hp_sizing_correlation.png (scatter, log-log)
        printed summary (n, median ratio, IQR) to stdout
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ERS_DIR = Path(r"C:\ERS\web")
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
PROVINCES = ["ON", "QC", "AB", "BC", "MB", "NS", "SK"]

COLS = ["HeatPump_Addition", "Post_HeatLoss", "Post_HPCapacity47", "Post_HPColdClimate"]


def load_all():
    frames = []
    for prov in PROVINCES:
        path = ERS_DIR / f"ers_web_{prov}.parquet"
        if not path.exists():
            print(f"[skip] {path} not found")
            continue
        df = pd.read_parquet(path, columns=COLS)
        df["province"] = prov
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main():
    df = load_all()
    n_total = len(df)

    has_hp = df["HeatPump_Addition"].fillna(False).astype(bool)
    n_hp = int(has_hp.sum())

    sub = df.loc[has_hp, ["Post_HeatLoss", "Post_HPCapacity47", "Post_HPColdClimate"]].copy()
    sub["Post_HeatLoss"] = pd.to_numeric(sub["Post_HeatLoss"], errors="coerce")
    sub["Post_HPCapacity47"] = pd.to_numeric(sub["Post_HPCapacity47"], errors="coerce")

    n_no_design_load = int(sub["Post_HeatLoss"].isna().sum())
    n_no_cert_cap = int(sub["Post_HPCapacity47"].isna().sum())

    clean = sub.dropna(subset=["Post_HeatLoss", "Post_HPCapacity47"])
    clean = clean[(clean["Post_HeatLoss"] > 0) & (clean["Post_HPCapacity47"] > 0)]
    n_clean = len(clean)

    ratio = clean["Post_HPCapacity47"] / clean["Post_HeatLoss"]

    print(f"ERS homes (7 provinces): {n_total:,}")
    print(f"Homes with a heat pump added this retrofit: {n_hp:,} ({100*n_hp/n_total:.2f}%)")
    print(f"  of those: no post-retrofit design heat loss recorded: {n_no_design_load:,}")
    print(f"  of those: no AHRI-certified 47F capacity resolved: {n_no_cert_cap:,}")
    print(f"  usable pairs (both present, both > 0): {n_clean:,} "
          f"({100*n_clean/n_hp:.1f}% of HP-addition homes)")
    print()
    print(f"Capacity / design-load ratio -- median {ratio.median():.2f}, "
          f"IQR [{ratio.quantile(0.25):.2f}, {ratio.quantile(0.75):.2f}], "
          f"10-90pct [{ratio.quantile(0.10):.2f}, {ratio.quantile(0.90):.2f}]")
    print(f"  share undersized (ratio < 0.8): {100*(ratio < 0.8).mean():.1f}%")
    print(f"  share ~matched (0.8-1.2):       {100*((ratio >= 0.8) & (ratio <= 1.2)).mean():.1f}%")
    print(f"  share oversized (ratio > 1.2):  {100*(ratio > 1.2).mean():.1f}%")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 6))
    ax.scatter(clean["Post_HeatLoss"], clean["Post_HPCapacity47"], s=6, alpha=0.15, color="#3D8065")
    lims = [0.1, max(clean["Post_HeatLoss"].max(), clean["Post_HPCapacity47"].max()) * 1.05]
    ax.plot(lims, lims, "--", color="#999", linewidth=1, label="capacity = design load (ratio 1.0)")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel("Post-retrofit design heat loss, EGHDESHTLOSS (kW)")
    ax.set_ylabel("Installed HP capacity @ 47F, AHRI-certified (kW)")
    ax.set_title(f"Installed HP capacity vs. home design load\n"
                 f"n={n_clean:,} ERS homes with a heat pump added, 7 provinces")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    out_png = OUT_DIR / "hp_sizing_correlation.png"
    fig.savefig(out_png, dpi=140)
    print(f"\n[out] wrote {out_png}")


if __name__ == "__main__":
    main()
