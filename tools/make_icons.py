#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build assets/icon.ico, assets/icon.icns and assets/icon-256.png from assets/icon.png.

    python3 tools/make_icons.py

The PNG is the source of truth (1024×1024, RGBA). Pillow writes the other sizes.
"""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "icon.png")
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main():
    if not os.path.isfile(SRC):
        sys.exit("missing %s" % SRC)
    im = Image.open(SRC).convert("RGBA")
    if im.size != (1024, 1024):
        im = im.resize((1024, 1024), Image.Resampling.LANCZOS)
        im.save(SRC)
    out256 = os.path.join(ROOT, "assets", "icon-256.png")
    im.resize((256, 256), Image.Resampling.LANCZOS).save(out256)
    ico = os.path.join(ROOT, "assets", "icon.ico")
    # BMP frames: Explorer and the installer often show the generic exe icon
    # when the small frames are PNG.
    im.save(ico, format="ICO", sizes=[(s, s) for s in ICO_SIZES], bitmap_format="bmp")
    icns = os.path.join(ROOT, "assets", "icon.icns")
    im.save(icns, format="ICNS")
    print("wrote", out256)
    print("wrote", ico)
    print("wrote", icns)


if __name__ == "__main__":
    main()
