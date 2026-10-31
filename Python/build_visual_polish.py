"""Prepare compact artwork and apply shared presentation to ten tools and hub.

Inputs: approved assets/icons/*.png, existing HTML pages and Geothermal template.
Outputs: visually balanced 512x216 WebP artwork and presentation-only markup.
Does not read or regenerate datasets. Requires Pillow. Run from any directory.
"""
from pathlib import Path
import math,re
from PIL import Image
from build_brand_assets import SPECS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets'/'icons'/'web'

def artwork():
    OUT.mkdir(exist_ok=True)
    for _,name,*_ in SPECS:
        im=Image.open(ROOT/'assets'/'icons'/f'{name}.png').convert('RGBA')
        alpha=im.getchannel('A');bbox=alpha.point(lambda n:255 if n>32 else 0).getbbox()
        im=im.crop(bbox)
        mass=sum(im.getchannel('A').histogram()[32:])
        scale=min(464/im.width,168/im.height,math.sqrt(26000/max(1,mass)))
        im=im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale))),Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(512,216));canvas.alpha_composite(im,((512-im.width)//2,(216-im.height)//2))
        canvas.save(OUT/f'{name}.webp',quality=90,method=6)

def patch(page,tool,name):
    p=ROOT/page;raw=p.read_bytes();text=raw.decode('utf-8');nl='\r\n' if b'\r\n' in raw else '\n'
    prefix='../../' if tool=='geothermal' else ''
    if 'data-energy-tool=' not in text:
        text=re.sub(r'<body\b',f'<body data-energy-tool="{tool}"',text,count=1)
    if 'visual-polish.css' not in text:
        text=text.replace('</head>',f'<link rel="stylesheet" href="{prefix}assets/visual-polish.css">\n<script defer src="{prefix}assets/visual-polish.js"></script>\n</head>',1)
    if tool=='index':
        text=re.sub(r'src="assets/icons/([^/]+)\.png"',r'src="assets/icons/web/\1.webp"',text)
        text=text.replace('width="200" height="84"','width="512" height="216" loading="lazy" decoding="async"')
        text=text.replace('Eight interactive tools built from public data','Ten interactive tools built from public data')
    elif tool=='geothermal':
        if 'map-title-art' not in text:
            text=text.replace('<div id="title" class="panel">','<div id="title" class="panel">\n<img class="map-title-art" src="../../assets/icons/web/geothermal.webp" alt="" width="512" height="216">')
        text=text.replace('{ collapsed: false }',"{ collapsed: window.matchMedia('(max-width:640px)').matches }")
    elif 'class="tool-heading"' not in text:
        text=re.sub(r'(<h1\b[^>]*>.*?</h1>)',lambda m:f'<div class="tool-heading"><img class="tool-heading-art" src="assets/icons/web/{name}.webp" alt="" width="512" height="216">'+m[1]+'</div>',text,count=1,flags=re.S)
    # These headers had anonymous unwrappable flex groups and overflowed phones.
    if tool in ['grid','retrofit-insights']:
        text=re.sub(r'<div style="display:flex;align-items:center;gap:(?:12|14)px">','<div class="header-tools">',text,count=1)
        if 'class="header-links"' not in text:
            text=re.sub(r'(<div class="header-tools">\s*)((?:<a class="sibling-link"[^>]*>.*?</a>\s*)+)',lambda m:m[1]+'<nav class="header-links" aria-label="Related tools">'+m[2]+'</nav>',text,count=1,flags=re.S)
    p.write_bytes(text.replace('\r\n','\n').replace('\n',nl).encode('utf-8'))

if __name__=='__main__':
    artwork()
    for slug,name,_,_,_,page in SPECS:patch(page,slug,name)
    patch('index.html','index',None)
    patch('Geothermal/scripts/map_template.html','geothermal','geothermal')
    print('Prepared ten balanced WebP assets and presentation markup for hub + ten tools.')
