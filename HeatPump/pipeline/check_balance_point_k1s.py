"""
Sketch: per-house "0-heat" balance-point temperature from ERS pre-retrofit
data, FSA K1S (Ottawa) only.

WHY THIS EXISTS
----------------
Follow-up on the sizing-correlation check: instead of comparing installed HP
capacity to design load, this asks a different question per HOUSEID -- at what
outdoor temperature does the home's own heating stop being needed? That
"balance point" plus the design-day peak load together describe a straight-
line load-vs-temperature curve per house, which is what a heat-pump sizing
tool ultimately needs.

METHOD (explicitly simplified -- confirmed with user 2026-08-11)
------------------------------------------------------------------
Two anchors per house, no internal/solar gains term:

  1. Peak load at the design temp:  Pre_HeatLoss (kW), EGHDESHTLOSS, at
     Ottawa's design temp T_design = -24.1 C (house-weighted mean over real
     ERS homes' own weather stations -- HeatPump/data/processed/
     city_design_temps.json, "Ottawa-Gatineau"). Same value for every K1S
     house in this sketch -- it is a city constant, not per-house station
     data (a real per-house join would use build_city_design_temps.py's
     houseid->station cache; skipped here).
  2. Annual heating energy: Pre_HeatEnergy (kWh), EGHFURNACEAEC.

Load model: load(T) = slope * (T0 - T) for T <= T0, else 0, where
slope = Pre_HeatLoss / (T0 - T_design) kW/C. T0 (the balance point) is the
one unknown -- solved by root-finding so that integrating load(T) over
Ottawa's 8760 TMY hours (HeatPump/data/processed/tmy_temps.json) reproduces
the house's own Pre_HeatEnergy.

This is a straight-line (no-gains) simplification: a real home's balance
point sits below its indoor setpoint because internal/solar gains offset
some loss. Skipping that here means T0 is best read as an "effective"
balance point that also absorbs whatever gains, occupant behaviour and
weather-year deviation separate the TMY year from the home's own year --
not a physical measurement.

DATA HONESTY
------------
Houses are dropped (counted, not silently) if:
  - Pre_HeatLoss or Pre_HeatEnergy missing/<=0
  - implied T0 has no root in [T_design + 0.5, 30] C -- i.e. the measured
    annual energy is inconsistent with this straight-line model at any
    plausible balance point (too low to reach even T0 = T_design+0.5, or
    too high to reach even T0 = 30 C)

INPUT:  C:\\ERS\\web\\ers_web_ON.parquet
        HeatPump/data/processed/city_design_temps.json (Ottawa-Gatineau design temp)
        HeatPump/data/processed/tmy_temps.json (Ottawa hourly TMY)
OUTPUT: data/interim/balance_point_k1s.csv (per house: HOUSEID, HeatLoss,
        HeatEnergy, slope, T0)
        data/interim/balance_point_k1s.png (all per-house lines + median)
        printed summary to stdout

STATUS: standalone sketch, not wired into the engine or the page.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq

ERS_PATH = Path(r"C:\ERS\web\ers_web_ON.parquet")
HP_DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
FSA = "K1S"
CITY_KEY = "Ottawa-Gatineau"   # city_design_temps.json key
TMY_KEY = "Ottawa"             # tmy_temps.json key
T0_MIN_MARGIN = 0.5            # C above T_design -- avoid the slope blowing up
T0_MAX = 30.0                  # C -- generous upper bound on a balance point


def load_design_temp() -> float:
    d = json.loads((HP_DATA / "city_design_temps.json").read_text(encoding="utf-8"))
    return d["cities"][CITY_KEY]["design_temp_C"]


def load_tmy_hours() -> np.ndarray:
    d = json.loads((HP_DATA / "tmy_temps.json").read_text(encoding="utf-8"))
    hours = d[TMY_KEY]
    # each entry is either a bare number or {"temp_c": ...}; handle both
    if hours and isinstance(hours[0], dict):
        return np.array([h["temp_c"] for h in hours], dtype=float)
    return np.array(hours, dtype=float)


def predicted_annual_kwh(t0: float, t_design: float, heat_loss_kw: float, tmy: np.ndarray) -> float:
    slope = heat_loss_kw / (t0 - t_design)  # kW/C
    load = np.clip(slope * (t0 - tmy), 0, None)  # kW at each of 8760 hours
    return load.sum()  # kWh (1 hour per sample)


def solve_t0(t_design: float, heat_loss_kw: float, heat_energy_kwh: float, tmy: np.ndarray):
    lo = t_design + T0_MIN_MARGIN
    hi = T0_MAX

    def f(t0):
        return predicted_annual_kwh(t0, t_design, heat_loss_kw, tmy) - heat_energy_kwh

    f_lo, f_hi = f(lo), f(hi)
    if f_lo > 0:
        return None, "energy_too_low"   # even the tightest balance point overshoots
    if f_hi < 0:
        return None, "energy_too_high"  # even T0=30C undershoots
    return brentq(f, lo, hi), "ok"


def main():
    t_design = load_design_temp()
    tmy = load_tmy_hours()
    print(f"Ottawa design temp ({CITY_KEY}): {t_design:.1f} C")
    print(f"TMY hours loaded: {len(tmy)}, min {tmy.min():.1f} C, max {tmy.max():.1f} C")

    df = pd.read_parquet(ERS_PATH, columns=["HOUSEID", "FSA", "Pre_HeatLoss", "Pre_HeatEnergy"])
    sub = df[df["FSA"] == FSA].copy()
    n_fsa = len(sub)

    sub["Pre_HeatLoss"] = pd.to_numeric(sub["Pre_HeatLoss"], errors="coerce")
    sub["Pre_HeatEnergy"] = pd.to_numeric(sub["Pre_HeatEnergy"], errors="coerce")

    valid = sub[(sub["Pre_HeatLoss"] > 0) & (sub["Pre_HeatEnergy"] > 0)].copy()
    n_missing = n_fsa - len(valid)

    t0s, slopes, reasons = [], [], []
    for hl, he in zip(valid["Pre_HeatLoss"], valid["Pre_HeatEnergy"]):
        t0, reason = solve_t0(t_design, hl, he, tmy)
        t0s.append(t0)
        reasons.append(reason)
        slopes.append(hl / (t0 - t_design) if t0 is not None else np.nan)
    valid["T0"] = t0s
    valid["slope_kw_per_C"] = slopes
    valid["_reason"] = reasons

    ok = valid[valid["_reason"] == "ok"].copy()
    n_too_low = int((valid["_reason"] == "energy_too_low").sum())
    n_too_high = int((valid["_reason"] == "energy_too_high").sum())

    print(f"\nFSA {FSA}: {n_fsa:,} homes")
    print(f"  missing/nonpositive Pre_HeatLoss or Pre_HeatEnergy: {n_missing:,}")
    print(f"  measured energy too low for any T0 in [{t_design + T0_MIN_MARGIN:.1f}, {T0_MAX:.0f}] C "
          f"(model overshoots even at the tightest balance point): {n_too_low:,}")
    print(f"  measured energy too high for any T0 up to {T0_MAX:.0f} C "
          f"(model undershoots even with heat needed almost always): {n_too_high:,}")
    print(f"  solved: {len(ok):,} ({100*len(ok)/n_fsa:.1f}% of FSA)")

    print(f"\nBalance point T0 (C) -- median {ok['T0'].median():.1f}, "
          f"IQR [{ok['T0'].quantile(0.25):.1f}, {ok['T0'].quantile(0.75):.1f}], "
          f"10-90pct [{ok['T0'].quantile(0.10):.1f}, {ok['T0'].quantile(0.90):.1f}]")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / "balance_point_k1s.csv"
    ok[["HOUSEID", "Pre_HeatLoss", "Pre_HeatEnergy", "slope_kw_per_C", "T0"]].to_csv(out_csv, index=False)
    print(f"\n[out] wrote {out_csv}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 6))
    t_axis = np.linspace(t_design, T0_MAX, 100)
    for hl, t0, slope in zip(ok["Pre_HeatLoss"], ok["T0"], ok["slope_kw_per_C"]):
        load = np.clip(slope * (t0 - t_axis), 0, None)
        ax.plot(t_axis, load, color="#3D8065", alpha=0.03, linewidth=0.8)

    med_t0 = ok["T0"].median()
    med_slope = ok["slope_kw_per_C"].median()
    med_hl = ok["Pre_HeatLoss"].median()
    med_load = np.clip(med_slope * (med_t0 - t_axis), 0, None)
    ax.plot(t_axis, med_load, color="#0B2545", linewidth=2.5,
            label=f"median (T0={med_t0:.1f}C, peak={med_hl:.1f}kW)")

    ax.axvline(t_design, color="#999", linestyle="--", linewidth=1, label=f"Ottawa design temp {t_design:.1f}C")
    ax.set_xlabel("Outdoor temperature (C)")
    ax.set_ylabel("Implied heating load (kW)")
    ax.set_title(f"Per-house load-vs-temperature lines, FSA {FSA} (n={len(ok):,})\n"
                 f"anchored on Pre_HeatLoss (design) + Pre_HeatEnergy (annual), no gains term")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xlim(t_design, T0_MAX)
    fig.tight_layout()
    out_png = OUT_DIR / "balance_point_k1s.png"
    fig.savefig(out_png, dpi=140)
    print(f"[out] wrote {out_png}")


if __name__ == "__main__":
    main()
