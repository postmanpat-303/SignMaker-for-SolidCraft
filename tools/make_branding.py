#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the Windows installer bitmaps from assets/icon.png (needs Pillow).

    python3 tools/make_branding.py

Outputs: packaging/windows/welcome.bmp  164x314  NSIS welcome/finish page
         packaging/windows/header.bmp   150x57   NSIS page header
Same layout as the installers for Del's other apps: a dark gradient side
panel with the icon, a blueprint grid and an accent bar.
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
BLUE = (7, 145, 255)
DEEP = (8, 18, 36)
NAVY = (10, 52, 110)
GOLD = (255, 196, 32)


def gradient(size, top, bottom):
    w, h = size
    g = Image.new("RGBA", size)
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    return g


def grid(im, step, alpha):
    """Faint CAD blueprint grid."""
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x in range(0, im.width, step):
        d.line([(x, 0), (x, im.height)], fill=BLUE + (alpha,))
    for y in range(0, im.height, step):
        d.line([(0, y), (im.width, y)], fill=BLUE + (alpha,))
    im.alpha_composite(layer)


def shadowed(canvas, im, xy, blur=5, alpha=170):
    pad = blur * 3
    sh = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    a = im.getchannel("A").point(lambda v: v * alpha // 255)
    blk = Image.new("RGBA", im.size, (0, 0, 0, 255))
    blk.putalpha(a)
    sh.alpha_composite(blk, (pad, pad))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(sh, (xy[0] - pad, xy[1] - pad + blur // 2))
    canvas.alpha_composite(im, xy)


def font(size, bold=True):
    for name in (("DejaVuSans-Bold.ttf", "arialbd.ttf") if bold else ("DejaVuSans.ttf", "arial.ttf")):
        for d in ("/usr/share/fonts/truetype/dejavu", "C:/Windows/Fonts", ""):
            try:
                return ImageFont.truetype(os.path.join(d, name), size)
            except OSError:
                pass
    return ImageFont.load_default()


def centred(d, y, text, f, fill, width):
    w = d.textlength(text, font=f)
    d.text(((width - w) / 2, y), text, font=f, fill=fill)


icon = Image.open(P("assets", "icon.png")).convert("RGBA")

wel = gradient((164, 314), DEEP, NAVY)
grid(wel, 12, 28)
glow = Image.new("RGBA", wel.size, (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse((14, 34, 150, 170), fill=BLUE + (90,))
wel.alpha_composite(glow.filter(ImageFilter.GaussianBlur(22)))
ic = icon.resize((124, 124), Image.Resampling.LANCZOS)
shadowed(wel, ic, (20, 42))
d = ImageDraw.Draw(wel)
centred(d, 190, "Sign Maker", font(19), (255, 255, 255), 164)
centred(d, 216, "for SolidCraft", font(12, False), (190, 220, 255), 164)
centred(d, 284, "by Del (postmanpat)", font(10, False), (150, 175, 210), 164)
d.rectangle((0, 309, 164, 314), fill=GOLD + (255,))
wel.convert("RGB").save(P("packaging", "windows", "welcome.bmp"))

hdr = Image.new("RGBA", (150, 57), (255, 255, 255, 255))
band = gradient((150, 57), NAVY, DEEP)
grid(band, 8, 40)
mask = Image.new("L", (150, 57), 0)
ImageDraw.Draw(mask).polygon([(14, 0), (150, 0), (150, 57), (0, 57)], fill=255)
hdr.paste(band, (0, 0), mask)
ic = icon.resize((47, 47), Image.Resampling.LANCZOS)
hdr.alpha_composite(ic, (150 - 47 - 8, 5))
ImageDraw.Draw(hdr).line([(0, 56), (150, 56)], fill=GOLD + (255,), width=2)
hdr.convert("RGB").save(P("packaging", "windows", "header.bmp"))
print("wrote packaging/windows/welcome.bmp and header.bmp")
