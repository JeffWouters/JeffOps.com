#!/usr/bin/env python3
"""Regenerate every favicon and app icon from static/JeffOps-Element.svg.

Run by hand, not by the build. The icons are committed artefacts: a build that
rewrote them on every run would churn binary files in git for no reason, and
would quietly change the site's face if the source SVG were ever edited by
accident.

    python tools/make_icons.py

Two decisions worth knowing about, because neither is reversible by tweaking a
number afterwards.

Which icons are transparent and which are not is a per-icon call, not a global
one, because the platforms disagree about what they do with an alpha channel.

The browser tab icons (favicon.ico and the two PNGs) and the Windows tile are
transparent. That is Jeff's call and it is the right one for the tile — the
tile spec expects a transparent logo over the TileColor that browserconfig.xml
already declares, so a black square there was fighting the platform. The known
cost on the tab icons: #00D9FF on a light tab strip measures about 1.7:1, so
in a light-mode browser the mark is present but low-contrast. On every dark
theme, and on the Windows tile, it reads correctly.

apple-touch-icon and the two android-chrome icons stay opaque, because
transparency there does not degrade, it breaks. iOS composites the touch icon
onto white and applies its own corner mask, so a transparent one lands as a
cyan smear on a white tile. The android-chrome pair are the manifest icons; a
launcher or an installed PWA puts them on its own surface, which is why the
manifest declares background_color #0a0c0f — baking that same colour into the
icon is what keeps the two agreeing.

safari-pinned-tab.svg is a silhouette in solid black. Safari ignores the
colours in that file entirely and paints the shape with whatever the page's
mask-icon colour says, so anything but a flat fill is wasted — and a gradient,
which is what the old file had traced into it, comes out as a solid blob.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'static' / 'JeffOps-Element.svg'
OUT = ROOT / 'static'

CYAN = '#00D9FF'
BACKDROP = (10, 12, 15)          # --bg
RENDER_WIDTH = 2048              # rasterise once, large, then downsample

# name -> (size, padding as a fraction of the square, opaque backdrop?)
# The small sizes get less padding: at 16px, four pixels of margin is a
# quarter of the icon and the mark stops being identifiable.
# See the module docstring for why the last column is not the same everywhere.
ICONS = {
    'favicon-16x16.png': (16, 0.02, False),
    'favicon-32x32.png': (32, 0.04, False),
    'apple-touch-icon.png': (180, 0.10, True),
    'android-chrome-192x192.png': (192, 0.08, True),
    'android-chrome-512x512.png': (512, 0.08, True),
    'mstile-150x150.png': (270, 0.16, False),  # Windows crops tiles; keep well inside
}
ICO_SIZES = (16, 32, 48)


async def rasterise(width: int) -> Path:
    """Render the SVG to a transparent PNG at the given width."""
    from playwright.async_api import async_playwright
    svg = SOURCE.read_text(encoding='utf-8')
    box = re.search(r'viewBox="([\d.\s\-]+)"', svg)
    vx, vy, vw, vh = (float(v) for v in box.group(1).split())
    height = round(width * vh / vw)
    page_html = (
        f'<html><body style="margin:0;background:transparent">'
        f'<div style="width:{width}px;height:{height}px;color:{CYAN};line-height:0">{svg}</div>'
        f'<style>svg{{width:{width}px;height:{height}px;display:block}}'
        f'.jeffops-mark{{color:{CYAN} !important}}</style></body></html>')
    target = Path('/tmp/icon-source.png')
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': width, 'height': height})
        await page.set_content(page_html)
        await page.screenshot(path=str(target), omit_background=True)
        await browser.close()
    return target


def square(mark: Image.Image, size: int, pad: float, opaque: bool = True) -> Image.Image:
    """Centre the mark on a square, scaled to fit inside the padding.

    opaque=False leaves the square fully transparent, so the mark sits on
    whatever the platform paints behind it.
    """
    canvas = Image.new('RGBA', (size, size),
                       BACKDROP + (255,) if opaque else (0, 0, 0, 0))
    inner = max(1, round(size * (1 - 2 * pad)))
    scaled = mark.copy()
    scaled.thumbnail((inner, inner), Image.LANCZOS)
    canvas.paste(scaled,
                 ((size - scaled.width) // 2, (size - scaled.height) // 2),
                 scaled)
    return canvas


def write_ico(target: Path, frames: list[Image.Image]) -> None:
    """Write a multi-size .ico with PNG-encoded frames.

    Pillow will not do this. Its ICO writer takes one image and a list of sizes
    and downscales that image itself, so the 16px frame comes out as a naive
    reduction of the 48px one — which is exactly the frame that needs its own
    padding to stay legible. Written by hand instead: the container is a
    six-byte header, a sixteen-byte entry per frame, and the PNG bytes. Every
    browser still in use reads PNG-in-ICO.
    """
    import io
    import struct

    blobs = []
    for frame in frames:
        buf = io.BytesIO()
        frame.save(buf, 'PNG', optimize=True)
        blobs.append(buf.getvalue())

    header = struct.pack('<HHH', 0, 1, len(frames))     # reserved, type 1 = icon, count
    offset = len(header) + 16 * len(frames)
    directory, payload = b'', b''
    for frame, blob in zip(frames, blobs):
        # 0 in the width/height byte means 256; nothing here is that large.
        directory += struct.pack('<BBBBHHII',
                                 frame.width if frame.width < 256 else 0,
                                 frame.height if frame.height < 256 else 0,
                                 0, 0, 1, 32, len(blob), offset)
        payload += blob
        offset += len(blob)
    target.write_bytes(header + directory + payload)


def pinned_tab_svg() -> str:
    """A flat black silhouette of the mark, for Safari's mask icon."""
    svg = SOURCE.read_text(encoding='utf-8')
    svg = re.sub(r'<style>.*?</style>', '', svg, flags=re.S)
    svg = re.sub(r'\sclass="[^"]*"', '', svg)
    svg = re.sub(r'\sstyle="[^"]*"', '', svg)
    svg = re.sub(r'\sfill="[^"]*"', '', svg)
    # One fill on the root; Safari repaints it anyway, but a file that renders
    # as a black silhouette on its own is a file you can check by opening it.
    svg = svg.replace('<svg ', '<svg fill="#000000" ', 1)
    header = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<!-- Safari mask icon. Flat black on purpose: Safari discards the\n'
              '     colours here and paints the shape with the mask-icon colour\n'
              '     declared on the page. Generated by tools/make_icons.py. -->\n')
    return header + re.sub(r'<\?xml[^>]*\?>\s*', '', svg).strip() + '\n'


async def main() -> int:
    if not SOURCE.exists():
        print(f'No source at {SOURCE}')
        return 1

    raster = await rasterise(RENDER_WIDTH)
    mark = Image.open(raster).convert('RGBA')
    mark = mark.crop(mark.getbbox())          # trim the SVG's own margin
    print(f'Rendered {SOURCE.name} at {mark.width}x{mark.height}')

    for name, (size, pad, opaque) in ICONS.items():
        square(mark, size, pad, opaque).save(OUT / name, optimize=True)
        print(f'  {name:<30}{size}x{size}  {"opaque" if opaque else "transparent":<12}'
              f'{(OUT / name).stat().st_size:>7} bytes')

    write_ico(OUT / 'favicon.ico',
              [square(mark, s, 0.02 if s <= 32 else 0.06, opaque=False)
               for s in ICO_SIZES])
    print(f'  {"favicon.ico":<30}{"/".join(str(s) for s in ICO_SIZES)}'
          f'      {(OUT / "favicon.ico").stat().st_size:>7} bytes')

    (OUT / 'safari-pinned-tab.svg').write_text(pinned_tab_svg(), encoding='utf-8')
    print(f'  {"safari-pinned-tab.svg":<30}silhouette'
          f'{(OUT / "safari-pinned-tab.svg").stat().st_size:>10} bytes')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
