"""Generate the social-preview (og:image) cards for every page in the suite.

Each page gets a 1200x630 PNG at ``assets/og/<slug>.png``, drawn in the site
palette (see ``assets/site-theme.css``) so a shared link looks like it belongs
to the suite. Pure-Pillow, no network: run it whenever a page's title or
one-line pitch changes.

    python Python/build_og_images.py

Fonts come from the local system (Georgia for the serif display face, a stand-in
for Fraunces; Arial for body, a stand-in for Inter). Both ship with Windows and
macOS; on Linux the script falls back to DejaVu.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "og"

W, H = 1200, 630

# Palette — light-theme values from assets/site-theme.css.
NAVY = (11, 37, 69)
AMBER = (232, 161, 36)
CREAM = (247, 244, 238)
MUTED = (154, 172, 194)
RULE = (32, 62, 99)

FONT_DIRS = [
    Path("C:/Windows/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path("/usr/share/fonts/truetype/dejavu"),
]
SERIF_BOLD = ["georgiab.ttf", "Georgia Bold.ttf", "DejaVuSerif-Bold.ttf"]
SANS = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]
SANS_BOLD = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"]


def load_font(candidates, size):
    for d in FONT_DIRS:
        for name in candidates:
            p = d / name
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def wrap(draw, text, font, max_width):
    """Greedy word wrap to a pixel width."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# slug -> (title, one-line pitch, source tag, path on the site)
CARDS = {
    "index": (
        "Canadian energy data, made explorable",
        "Eight interactive tools built from public data — how Canadians heat "
        "their homes, what gets built, and what powers the grid.",
        "Open data · no backend",
        "/",
    ),
    "retrofits": (
        "Retrofit Explorer",
        "1.45 million real Canadian home-energy retrofits — what homes like "
        "yours did, and what their audits say it saved.",
        "NRCan EnerGuide · 2004–2026",
        "/retrofits",
    ),
    "retrofit-insights": (
        "Retrofit Insights",
        "The national picture of 1.45M matched before/after audits: what "
        "works, where the worst stock sits, and where programs should look.",
        "NRCan EnerGuide · national view",
        "/retrofit-insights",
    ),
    "newhomes": (
        "New Homes Explorer",
        "How efficient new Canadian construction actually is — as-designed "
        "versus as-built EnerGuide evaluations.",
        "NRCan EnerGuide · new construction",
        "/newhomes",
    ),
    "heatpump": (
        "Heat Pump Explorer",
        "An hour-by-hour simulation of switching to a cold-climate heat pump "
        "in 14 cities: energy, emissions, cost and backup heat.",
        "ECCC weather · NEEP performance data",
        "/heatpump",
    ),
    "ceud": (
        "CEUD Explorer",
        "NRCan's Comprehensive Energy Use Database, made browsable — all five "
        "sectors, national and provincial.",
        "NRCan CEUD · 2000–present",
        "/ceud",
    ),
    "construction": (
        "Construction Tracker",
        "Building permits, housing starts and construction investment in one "
        "dashboard — national, provincial and metro.",
        "Statistics Canada · CMHC",
        "/construction",
    ),
    "grid": (
        "Grid Dashboard",
        "Ontario and Alberta generation mix and emissions intensity — plus "
        "why marginal emissions are the number that matters.",
        "IESO · AESO · updated weekly",
        "/grid",
    ),
    "project-atlas": (
        "Project Atlas",
        "Status, data sources and standing assumptions behind every tool in "
        "the suite.",
        "Internal reference",
        "/project-atlas",
    ),
}


def draw_card(slug, title, pitch, source, path):
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)

    f_mark = load_font(SANS_BOLD, 30)
    f_title = load_font(SERIF_BOLD, 68)
    f_pitch = load_font(SANS, 32)
    f_meta = load_font(SANS, 26)

    pad = 80

    # Wordmark: "ottawa" in cream, "visuals" in amber, matching the site header.
    d.text((pad, 66), "ottawa", font=f_mark, fill=CREAM)
    mark_w = d.textlength("ottawa", font=f_mark)
    d.text((pad + mark_w, 66), "visuals", font=f_mark, fill=AMBER)

    # The house glyph from the favicon, top-right.
    gx, gy, gs = W - pad - 64, 58, 64
    d.line(
        [
            (gx, gy + gs),
            (gx, gy + gs * 0.45),
            (gx + gs * 0.5, gy),
            (gx + gs, gy + gs * 0.45),
            (gx + gs, gy + gs),
        ],
        fill=AMBER,
        width=5,
        joint="curve",
    )

    # Title block, vertically centred in the middle band.
    title_lines = wrap(d, title, f_title, W - 2 * pad)
    pitch_lines = wrap(d, pitch, f_pitch, W - 2 * pad - 40)
    lh_t, lh_p = 84, 46
    block_h = len(title_lines) * lh_t + 26 + len(pitch_lines) * lh_p
    y = (H - block_h) // 2 + 10

    # Amber accent rule to the left of the title block.
    d.rectangle([pad, y + 12, pad + 6, y + len(title_lines) * lh_t - 10], fill=AMBER)

    for line in title_lines:
        d.text((pad + 30, y), line, font=f_title, fill=CREAM)
        y += lh_t
    y += 26
    for line in pitch_lines:
        d.text((pad + 30, y), line, font=f_pitch, fill=MUTED)
        y += lh_p

    # Footer rule + metadata.
    d.rectangle([pad, H - 118, W - pad, H - 117], fill=RULE)
    d.text((pad, H - 90), source, font=f_meta, fill=MUTED)
    url = f"ottawavisuals.github.io/Energy{'' if path == '/' else path}"
    url_w = d.textlength(url, font=f_meta)
    d.text((W - pad - url_w, H - 90), url, font=f_meta, fill=AMBER)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{slug}.png"
    img.save(dest, optimize=True)
    return dest


def main():
    for slug, (title, pitch, source, path) in CARDS.items():
        dest = draw_card(slug, title, pitch, source, path)
        print(f"{dest.relative_to(ROOT)}  {dest.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
