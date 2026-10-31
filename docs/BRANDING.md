# Tab icons and social previews

2026-10-31: shared tile/header styling and compact web artwork are documented in
[Visual polish](VISUAL_POLISH.md). That follow-up is local and not yet published.

Updated 2026-10-30. Published and verified live 2026-10-30.

Release: `gh-pages` commit `0b29bfd`; all 58 published files matched the release
on 2026-10-30. Existing data trees and Geothermal's embedded data were preserved.

The ten tools use the approved illustrations in `assets/icons/`. Each has a
separate, simplified native SVG tab icon and 32px PNG fallback under
`assets/favicons/`; these use the same navy, teal and amber palette on white
to preserve contrast in light and dark browser chrome.

Twelve 1200×630 social cards (ten tools, landing page, Project Atlas) use the
approved full artwork, brief editorial descriptions and source names.
Charts, heat waves and geological layers in artwork are conceptual, not data.
The landing page and Atlas use a collage of the ten approved illustrations.

`Python/build_brand_assets.py` rebuilds these from local PNG artwork and native
SVG symbols. It requires Pillow, Node.js and Sharp (build-time dependencies
only). Set `NODE_EXE` and `NODE_PATH` if they are not available on the usual
paths. Run from the repository root:

```text
python Python/build_brand_assets.py path/to/preview-sheet.jpg
```

The script writes versioned `assets/og/*-v2.png` files and updates Open Graph,
Twitter and favicon references in the twelve HTML pages. The older
`Python/build_og_images.py` still builds legacy cards, which are retained for
other existing references. No AC page or its assets were changed.

Geothermal's generated HTML is ignored on `main`. Its tracked
`Geothermal/scripts/map_template.html` also carries the metadata, so a later map
rebuild preserves the branding. Include the generated map HTML in a future
`gh-pages` publication; do not regenerate map data for a branding-only update.

Pre-publication verification: inspect the social-card sheet and small-size
favicons; verify all relative favicon paths and absolute image URLs resolve
locally, dimensions are 1200×630 / 32×32 and no card text overlaps its footer.
Sharing services can retain cached previews after publication.
