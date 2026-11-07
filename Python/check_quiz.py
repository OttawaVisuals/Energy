#!/usr/bin/env python3
"""check_quiz.py - invariants for the generated Energy Quiz banks.

INPUTS   quiz_json/meta.json, <topic>.json, icons.json, shapes.json (all produced by build_quiz.py)
OUTPUT   a pass/fail report on stdout; exit code 1 if any check fails. Writes nothing.
RUN      python Python/check_quiz.py        (after python Python/build_quiz.py)

Why: the page trusts the bank completely, so the promises on the page ("values differ after
display rounding", "gap of at least 3%", "no duplicates") are enforced here, per question:
  all      unique ids; difficulty easy/medium/hard (None only for estimate); finite values;
           every item has a region outline or an icon
  compare  2 distinct items, display strings differ, relative gap >= min_gap
  rank     3 distinct items (podium), distinct display strings, adjacent gaps >= min_gap
  insert   target not among the anchors, 4 anchors, strictly different values and labels
  gap      options ascending, answer is the option closest to the true ratio (and is in range)
  estimate value in 0..100, tolerances for all three levels, non-empty prompt
  history  2 distinct items, change values finite
It checks consistency of the bank, not the truth of the source data.
"""
import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "quiz_json"
errors = []


def bad(q, msg):
    errors.append(f"{q['id']}: {msg}")


def rel(a, b):
    return abs(a - b) / max(abs(a), abs(b)) if max(abs(a), abs(b)) else 0


def finite(*xs):
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in xs)


def check(q, min_gap, covered):
    s, it = q["s"], q["it"]
    names = [r[0] for r in it]
    if q.get("d") not in ("easy", "medium", "hard") and not (s == "estimate" and q.get("d") is None):
        bad(q, f"difficulty {q.get('d')!r}")
    if not all(finite(r[1]) for r in it + ([q["tg"]] if "tg" in q else [])):
        bad(q, "non-finite value")
        return
    for r in it + ([q["tg"]] if "tg" in q else []):
        if r[0] not in covered:
            bad(q, f"no icon or outline for {r[0]!r}")
    if s == "compare":
        if len(it) != 2 or len(set(names)) != 2:
            bad(q, "needs 2 distinct items")
        elif it[0][2] == it[1][2]:
            bad(q, "display strings tie")
        elif rel(it[0][1], it[1][1]) < min_gap - 1e-9:
            bad(q, f"gap {rel(it[0][1], it[1][1]):.3f} < {min_gap}")
    elif s == "rank":
        if len(it) != 3 or len(set(names)) != 3:
            bad(q, "needs 3 distinct items (podium)")
        else:
            v = sorted(it, key=lambda r: -r[1])
            if len({r[2] for r in it}) != len(it):
                bad(q, "display strings tie")
            for a, b in zip(v, v[1:]):
                if rel(a[1], b[1]) < min_gap - 1e-9:
                    bad(q, f"adjacent gap {a[0]}/{b[0]} < {min_gap}")
    elif s == "insert":
        tg = q["tg"]
        if len(it) != 4 or len(set(names)) != 4 or tg[0] in names:
            bad(q, "needs 4 distinct anchors, target not among them")
        elif tg[2] in {r[2] for r in it} or any(r[1] == tg[1] for r in it):
            bad(q, "target ties an anchor")
        else:
            sv = [r[1] for r in it]
            if sv != sorted(sv, reverse=True):
                bad(q, "anchors are not in highest-to-lowest order")
    elif s == "gap":
        op, an = q["op"], q["an"]
        if len(it) != 2 or len(set(names)) != 2:
            bad(q, "needs 2 distinct items")
            return
        if op != sorted(op) or len(set(op)) != len(op) or not 0 <= an < len(op):
            bad(q, "options not ascending/unique or answer index out of range")
            return
        ratio = max(it[0][1], it[1][1]) / min(it[0][1], it[1][1])
        best = min(range(len(op)), key=lambda i: abs(op[i] - ratio))
        if best != an:
            bad(q, f"answer {op[an]}x is not closest to true ratio {ratio:.2f}x")
    elif s == "estimate":
        if not 0 <= it[0][1] <= 100:
            bad(q, "share outside 0-100")
        if set(q.get("tol", {})) != {"easy", "medium", "hard"}:
            bad(q, "tolerances missing")
        if not q.get("pr"):
            bad(q, "empty prompt")
    elif s == "history":
        if len(it) != 2 or len(set(names)) != 2:
            bad(q, "needs 2 distinct items")
    else:
        bad(q, f"unknown style {s!r}")


def main():
    meta = json.load(open(OUT / "meta.json", encoding="utf-8"))
    min_gap = meta["min_gap"]
    covered = set()
    for f, key in (("icons.json", "items"), ("shapes.json", "names")):
        p = OUT / f
        if p.exists():
            covered |= set(json.load(open(p, encoding="utf-8"))[key])
        else:
            print(f"  (note: {f} missing - skipping that part of the coverage check)")
    ids, total, by_style = set(), 0, {}
    for t in meta["topics"]:
        tid = t["id"] if isinstance(t, dict) else t
        for q in json.load(open(OUT / f"{tid}.json", encoding="utf-8"))["questions"]:
            total += 1
            by_style[q["s"]] = by_style.get(q["s"], 0) + 1
            if q["id"] in ids:
                bad(q, "duplicate id")
            ids.add(q["id"])
            check(q, min_gap, covered)
    print(f"checked {total} questions {by_style}")
    if errors:
        print(f"FAIL: {len(errors)} problems; first 15:")
        for e in errors[:15]:
            print("  -", e)
        sys.exit(1)
    print("OK: all invariants hold")


if __name__ == "__main__":
    main()
