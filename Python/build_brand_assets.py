"""Build tab icons and 1200x630 social cards from approved local artwork.

Inputs: assets/icons/*.png and the editorial specs below. Outputs: native SVG
and 32px PNG favicons, versioned social cards, and page metadata. No network or
data processing. Run with Python/Pillow and Node/Sharp; existing AC assets stay unchanged.
"""
from pathlib import Path
import re
import sys
import subprocess
import os
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

from build_og_images import load_font, wrap, SERIF_BOLD, SANS, SANS_BOLD

ROOT = Path(__file__).resolve().parents[1]
NAVY, TEAL, AMBER = '#0B2545', '#009D9D', '#E8A124'
SPECS = [
 ('retrofits','retrofit-explorer','Retrofit Explorer','Explore home upgrades and audit-modelled energy savings across Canada.','NRCan EnerGuide','retrofits.html'),
 ('retrofit-insights','retrofit-insights','Retrofit Insights','Compare retrofit outcomes across regions, climates and communities.','NRCan EnerGuide · Statistics Canada','retrofit-insights.html'),
 ('newhomes','new-homes','New Homes Explorer','Compare new homes as designed with their finished, tested evaluations.','NRCan EnerGuide','newhomes.html'),
 ('ceud','ceud','CEUD Explorer','Explore where Canada uses energy, sector by sector.','NRCan CEUD','ceud.html'),
 ('construction','construction','Construction Tracker','Track building permits, housing starts and construction investment.','Statistics Canada · CMHC','construction.html'),
 ('permits','permits','Permits Explorer','Explore municipal building records, locations and approval timelines.','Municipal open data','permits.html'),
 ('grid','grid','Grid Dashboard','Explore electricity generation, demand and emissions in Ontario and Alberta.','IESO · AESO','grid.html'),
 ('districtenergy','district-energy','District Energy Explorer','Explore shared heating and cooling networks across Canada.','CEEDC · Simon Fraser University','districtenergy.html'),
 ('geothermal','geothermal','Ottawa Geothermal Map','Screen ground-source heat potential, drilling conditions and grid capacity.','Ontario WWIS · City of Ottawa','Geothermal/output/index.html'),
 ('heatpump','heat-pump','Heat Pump Explorer','Simulate home heating hour by hour: energy, emissions, cost and backup heat.','Weather · equipment · grid data','heatpump.html'),
]

# Deliberately simplified native symbols, rather than shrinking wide tile art.
SYMBOLS = {
 'retrofits':'<path d="M5 15 16 5 27 15v12H5Z"/><path d="M11 11 16 7 23 14v10H9v-9" stroke="#009D9D" stroke-width="3"/><path d="M16 14c-4 3 4 5 0 9" stroke="#E8A124"/>',
 'retrofit-insights':'<path d="M5 26V15h6v11m2 0V6h6v20m2 0V11h6v15" fill="#009D9D"/><path d="M4 27h24"/><circle cx="16" cy="7" r="3" fill="#E8A124" stroke="none"/>',
 'newhomes':'<path d="M4 14 16 4 28 14M7 12v16h18V12"/><path d="M12 28V18h8v10" stroke="#009D9D"/><path d="m24 5 1 3 3 1-3 1-1 3-1-3-3-1 3-1Z" fill="#E8A124" stroke="none"/>',
 'ceud':'<circle cx="16" cy="16" r="11" stroke="#009D9D" stroke-width="5"/><path d="M16 5v11h11" stroke="#E8A124" stroke-width="5"/>',
 'construction':'<path d="M9 28V5m-5 5h24L18 5H6m16 5v9m-3 0h6"/><path d="M15 28V17h11v11M5 28h23" stroke="#009D9D"/><path d="M4 6h24" stroke="#E8A124" stroke-width="3"/>',
 'permits':'<path d="M6 4h13l5 5v19H6Z"/><path d="M19 4v6h5M10 14h9m-9 5h6" stroke="#009D9D"/><circle cx="22" cy="22" r="5" fill="white" stroke="#E8A124"/><path d="m26 26 3 3"/>',
 'grid':'<path d="m16 4-8 24m8-24 8 24M6 12h20M9 7h14M4 20h24M11 12l10 8m0-8-10 8M7 28h4m10 0h4"/><path d="m17 10-5 8h5l-2 7 7-10h-5Z" fill="#E8A124" stroke="none"/>',
 'districtenergy':'<path d="M4 5h9v13H4Zm15 4h9v13h-9Z"/><path d="M8 18v6h15v-2" stroke="#E8A124" stroke-width="3"/><path d="M5 18v10h21v-6" stroke="#009D9D" stroke-width="3"/>',
 'geothermal':'<path d="M5 11 13 4l8 7M7 10v7h12v-7"/><path d="M3 19h26m-26 5h26" stroke="#009D9D"/><path d="M11 17v9a3 3 0 0 0 6 0v-9" stroke="#E8A124" stroke-width="3"/>',
 'heatpump':'<rect x="4" y="8" width="24" height="18" rx="3"/><circle cx="14" cy="17" r="6" stroke="#009D9D"/><path d="m14 12 2 5-5 3m3-3 4 4" stroke="#009D9D"/><path d="M24 10V4m-3 3h6" stroke="#E8A124"/>',
 'index':'<path d="M4 15 16 5l12 10M7 13v14h18V13"/><path d="m18 12-7 9h6l-2 6 8-10h-6Z" fill="#E8A124" stroke="none"/>',
 'project-atlas':'<rect x="4" y="4" width="9" height="9" rx="2" fill="#009D9D"/><rect x="19" y="4" width="9" height="9" rx="2"/><rect x="4" y="19" width="9" height="9" rx="2"/><rect x="19" y="19" width="9" height="9" rx="2" fill="#E8A124"/>',
}

def icon(slug):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="white"/><g fill="none" stroke="{NAVY}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{SYMBOLS[slug]}</g></svg>'
    ET.fromstring(svg)
    out = ROOT/'assets'/'favicons'
    out.mkdir(exist_ok=True)
    (out/f'{slug}.svg').write_text(svg, encoding='utf-8')
    # SVG is the primary tiny-size asset. PNG fallback rendered from the same source.
    subprocess.run([os.environ.get('NODE_EXE','node'), '-e',
        "require('sharp')(process.argv[1]).resize(32,32).png().toFile(process.argv[2]).catch(e=>{console.error(e);process.exit(1)})",
        str(out/f'{slug}.svg'), str(out/f'{slug}.png')],check=True)

def fitted_art(path, size):
    art = Image.open(path).convert('RGBA')
    art = art.crop(art.getbbox())
    art.thumbnail(size, Image.Resampling.LANCZOS)
    return art

def card(slug, art_name, title, pitch, source):
    im = Image.new('RGB',(1200,630),'#F7F4EE')
    d = ImageDraw.Draw(im)
    d.rectangle((0,0,1199,13),fill=AMBER)
    mark=load_font(SANS_BOLD,30)
    d.text((60,47),'ottawa',font=mark,fill=NAVY)
    x=60+d.textlength('ottawa',font=mark)
    d.text((x,47),'visuals',font=mark,fill='#9B650B')
    tf=load_font(SERIF_BOLD,54); pf=load_font(SANS,29)
    title_lines=wrap(d,title,tf,590); y=160
    for line in title_lines:
        d.text((60,y),line,font=tf,fill=NAVY);y+=68
    y+=24
    for line in wrap(d,pitch,pf,570):
        d.text((60,y),line,font=pf,fill='#4F6174');y+=41
    assert y < 503, (slug,'text overlaps footer')
    d.rounded_rectangle((680,126,1140,490),radius=24,fill='white')
    if art_name:
        art=fitted_art(ROOT/'assets'/'icons'/f'{art_name}.png',(420,310))
        im.paste(art,(910-art.width//2,308-art.height//2),art)
    else:
        for i,spec in enumerate(SPECS):
            art=fitted_art(ROOT/'assets'/'icons'/f'{spec[1]}.png',(190,55))
            cx=800+(i%2)*220;cy=166+(i//2)*69
            im.paste(art,(cx-art.width//2,cy-art.height//2),art)
    d.line((60,530,1140,530),fill='#D2D8E3',width=2)
    d.text((60,550),source,font=load_font(SANS,23),fill='#4F6174')
    d.text((60,586),'ottawavisuals.github.io/Energy',font=load_font(SANS,19),fill=NAVY)
    path=ROOT/'assets'/'og'/f'{slug}-v2.png';im.save(path,optimize=True)
    return im

def metadata(page, slug, title):
    path=ROOT/page
    raw=path.read_bytes();text=raw.decode('utf-8');nl='\r\n' if b'\r\n' in raw else '\n'
    prefix='../../' if page.startswith('Geothermal/') else ''
    tags=f'<link rel="icon" type="image/svg+xml" href="{prefix}assets/favicons/{slug}.svg">\n<link rel="icon" type="image/png" sizes="32x32" href="{prefix}assets/favicons/{slug}.png">'
    text=re.sub(r'<link\b[^>]*\brel=["\']icon["\'][^>]*>\s*','',text)
    text=text.replace('</head>',tags+'\n</head>',1)
    url=f'https://ottawavisuals.github.io/Energy/assets/og/{slug}-v2.png'
    if slug == 'geothermal' and 'property="og:description"' not in text:
        text=text.replace('</head>','<meta property="og:description" content="Screen ground-source heat potential, drilling conditions and grid capacity in Ottawa.">\n</head>',1)
    if 'property="og:image"' in text:
        text=re.sub(r'(<meta (?:property="og:image"|name="twitter:image") content=")[^"]+',lambda m:m[1]+url,text)
    else:
        tags=f'<meta property="og:title" content="{title}">\n<meta property="og:type" content="website">\n<meta property="og:url" content="https://ottawavisuals.github.io/Energy/Geothermal/output/">\n<meta property="og:image" content="{url}">\n<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n<meta property="og:image:alt" content="{title} social preview card">\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:image" content="{url}">'
        text=text.replace('</head>',tags+'\n</head>',1)
    path.write_bytes(text.replace('\r\n','\n').replace('\n',nl).encode('utf-8'))

def main():
    cards=[]
    for slug,art,title,pitch,source,page in SPECS:
        icon(slug);cards.append(card(slug,art,title,pitch,source));metadata(page,slug,title)
    for slug,title,pitch,page in [
        ('index','Canadian energy data','Explore home energy, construction and the systems that power Canada.','index.html'),
        ('project-atlas','Project Atlas','Explore the tools, sources and methods behind the Energy suite.','project-atlas.html')]:
        icon(slug);cards.append(card(slug,None,title,pitch,'Ottawa Visuals · Energy suite'));metadata(page,slug,title)
    preview=Image.new('RGB',(1200,840),'white')
    for i,im in enumerate(cards):
        preview.paste(im.resize((400,210)),((i%3)*400,(i//3)*210))
    target=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'assets'/'og'/'contact-sheet.jpg'
    target.parent.mkdir(parents=True,exist_ok=True);preview.save(target)
    print(f'Built {len(cards)} cards and favicon pairs. Preview: {target}')

if __name__=='__main__':main()
