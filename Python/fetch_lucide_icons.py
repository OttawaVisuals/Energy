#!/usr/bin/env python3
"""fetch_lucide_icons.py - vendor the Lucide icons the Energy Quiz uses.

Lucide (https://lucide.dev) is ISC-licensed: free to copy and embed provided the
copyright + permission notice is kept, so the LICENSE file is vendored beside the
icons. This is a ONE-OFF, build-time download (jsDelivr's npm mirror, version
pinned for reproducibility); the published site loads nothing from any CDN.

OUTPUT
  assets/vendor/lucide/<name>.svg   only the icons listed in ICONS below
  assets/vendor/lucide/LICENSE      Lucide's licence text (ISC, plus Feather's MIT notice)
  assets/vendor/lucide/VERSION      pinned lucide-static version

Run only to add or change icons:  python Python/fetch_lucide_icons.py
The quiz build (Python/build_quiz_icons.py) reads the vendored files, no network.
"""
import urllib.request
from pathlib import Path

VERSION = "1.70.0"
BASE = f"https://cdn.jsdelivr.net/npm/lucide-static@{VERSION}"
OUT = Path(__file__).resolve().parent.parent / "assets" / "vendor" / "lucide"

# Keep in sync with ICON_MAP in build_quiz_icons.py (it checks that every mapped icon is vendored).
ICONS = """zap flame droplet tree-pine ellipsis fuel barrel container plane
heater snowflake shower-head refrigerator lightbulb
building-2 caravan houses house building rows-3
bus wheat utensils drama graduation-cap stethoscope newspaper briefcase wrench store warehouse boxes
brick-wall flask-conical hard-hat trees anvil pickaxe factory cylinder scroll-text flame-kindling
car car-front van truck train-front ship tractor""".split()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "energy-quiz-build"})
    return urllib.request.urlopen(req, timeout=30).read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in sorted(set(ICONS)):
        svg = get(f"{BASE}/icons/{name}.svg")
        assert svg.lstrip().startswith(b"<svg") or svg.lstrip().startswith(b"<!--"), name
        (OUT / f"{name}.svg").write_bytes(svg)
    (OUT / "LICENSE").write_bytes(get(f"{BASE}/LICENSE"))
    (OUT / "VERSION").write_text(VERSION + "\n")
    print(f"vendored {len(set(ICONS))} icons from lucide-static@{VERSION} into {OUT}")


if __name__ == "__main__":
    main()
