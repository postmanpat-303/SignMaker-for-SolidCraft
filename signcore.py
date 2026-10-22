# -*- coding: utf-8 -*-
"""Sign Maker core: fonts, 2D preview, SolidCraft headless build, 3MF and dimension picture.
Author: Del (postmanpat). Built with Grok Bot."""
import os, sys, json, re, math, shutil, subprocess, tempfile, zipfile, time

def _application_dir():
    """Folder the user launched: next to the script, or next to a frozen executable.

    A PyInstaller macOS .app keeps the binary in Contents/MacOS. CLI search also
    looks beside the .app itself (see find_cli).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

APP_DIR = _application_dir()
HOME = os.path.expanduser("~")
# Older portable unpack, still checked last so existing setups keep working.
_OLD_CLI_ROOT = os.path.join(HOME, "Documents", "GrokPrograms", "SolidCraft")
CLI_MISSING_MSG = (
    "Could not find solidcraft-cli. Install SolidCraft from "
    "https://github.com/tangency-labs/solidcraft/releases and point Sign Maker "
    "at solidcraft-cli (solidcraft-cli.exe on Windows) with Browse.\n\n"
    "Windows: the MSI or the portable zip (the single-file .exe has no CLI).\n"
    "macOS: the separate solidcraft-cli zip, or inside SolidCraft.app.\n"
    "Linux: the .deb, .rpm or .tar.gz (or an extracted AppImage). "
    "The AppImage itself is the desktop app, not the CLI."
)

def _config_dir():
    """Settings live in the platform config folder."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(HOME, "AppData", "Roaming")
        return os.path.join(base, "SignMaker")
    if sys.platform == "darwin":
        return os.path.join(HOME, "Library", "Application Support", "SignMaker")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
    return os.path.join(base, "SignMaker")

def _work_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return os.path.join(base, "SignMaker", "work")
    if sys.platform == "darwin":
        return os.path.join(HOME, "Library", "Caches", "SignMaker", "work")
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache")
    return os.path.join(base, "SignMaker", "work")

DATA_DIR = _config_dir()
WORK_DIR = _work_dir()
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
FONT_CACHE = os.path.join(DATA_DIR, "fontcache.json")
CREATE_NO_WINDOW = 0x08000000

DEFAULTS = {
    "text": "Your Text",
    "font": "Times New Roman",
    "length": 63.0, "height": 15.0, "thickness": 0.8,
    "raise": 1.0, "margin": 1.5, "corner": 0.0,
    "auto_size": True, "text_size": 8.0,
    "bold": False, "spacing": 0.0, "style": "raised",
    "plate_color": "#FFFFFF", "text_color": "#000000",
    "stl": False,
    "cli_path": "",
    "output_dir": "",
    "auto_preview": True,
    "theme": "light",
    "favourites": [
        {"label": "Your Text (Times New Roman)", "text": "Your Text", "font": "Times New Roman"},
        {"label": "TELEPHONE (Times New Roman)", "text": "TELEPHONE", "font": "Times New Roman"},
    ],
}
COLOUR_PRESETS = [
    ("White", "#FFFFFF"), ("Black", "#000000"), ("An Post green", "#00A769"),
    ("Post-box red", "#C8102E"), ("Gold", "#D4AF37"), ("Silver", "#C0C0C0"),
    ("Navy", "#1F3A93"), ("Cream", "#F3E9D2"),
]

# ---------------------------------------------------------------- settings
def load_settings():
    s = json.loads(json.dumps(DEFAULTS))
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    return s

def save_settings(s):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SETTINGS_PATH)

# ---------------------------------------------------------------- paths
def documents_dir():
    """~/Documents on every OS. Created when a sign is saved, if it is missing."""
    return os.path.join(os.path.expanduser("~"), "Documents")

def default_output_dir():
    """~/Documents/Sign Maker/Signs — one subfolder per wording is added later."""
    return os.path.join(documents_dir(), "Sign Maker", "Signs")

def output_root(settings=None):
    """Folder that holds the per-wording sign folders. Blank setting = the default."""
    if settings is None:
        settings = load_settings()
    custom = (settings.get("output_dir") or "").strip().strip('"')
    return custom or default_output_dir()

def _cli_names():
    """Filenames SolidCraft actually ships. .exe is Windows; the bare name is macOS and Linux."""
    if os.name == "nt":
        return ("solidcraft-cli.exe",)
    return ("solidcraft-cli", "solidcraft-cli.exe")

def _version_key(path):
    folder = os.path.basename(os.path.dirname(path))
    nums = tuple(int(x) for x in re.findall(r"\d+", folder))
    return (nums, folder.lower())

def _best_existing(paths):
    found, seen = [], set()
    for p in paths:
        if not p or not os.path.isfile(p):
            continue
        key = os.path.normcase(os.path.abspath(p))
        if key in seen:
            continue
        seen.add(key)
        found.append(os.path.abspath(p))
    if not found:
        return None
    return sorted(found, key=_version_key)[-1]

def _cli_in_named_trees(base):
    """solidcraft-cli inside a folder whose name mentions SolidCraft, one or two levels down."""
    hits = []
    if not base or not os.path.isdir(base):
        return hits
    try:
        entries = os.listdir(base)
    except OSError:
        return hits
    for ent in entries:
        low = ent.lower()
        if "solidcraft" not in low and "solvecraft" not in low:
            continue
        folder = os.path.join(base, ent)
        if not os.path.isdir(folder):
            continue
        for n in _cli_names():
            hits.append(os.path.join(folder, n))
        try:
            children = os.listdir(folder)
        except OSError:
            continue
        for child in children:
            sub = os.path.join(folder, child)
            if os.path.isdir(sub):
                for n in _cli_names():
                    hits.append(os.path.join(sub, n))
    return hits

def _beside_app_paths():
    """CLI sitting next to the script, the frozen exe, or a macOS .app bundle."""
    dirs = [APP_DIR]
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        bundle = os.path.dirname(os.path.dirname(APP_DIR))
        if bundle.endswith(".app"):
            dirs.append(bundle)
            dirs.append(os.path.dirname(bundle))
    paths = []
    for d in dirs:
        for n in _cli_names():
            paths.append(os.path.join(d, n))
        paths += _cli_in_named_trees(d)
    return paths

def _install_paths():
    """Common per-OS install locations for solidcraft-cli."""
    paths = []
    home = HOME
    if os.name == "nt":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        roots = [
            os.path.join(pf, "SolidCraft"),
            os.path.join(pf86, "SolidCraft"),
            os.path.join(local, "Programs", "SolidCraft"),
            os.path.join(local, "SolidCraft"),
            os.path.join(home, "scoop", "apps", "solidcraft", "current"),
        ]
        for root in roots:
            for n in _cli_names():
                paths.append(os.path.join(root, n))
    elif sys.platform == "darwin":
        for apps in ("/Applications", os.path.join(home, "Applications")):
            macos = os.path.join(apps, "SolidCraft.app", "Contents", "MacOS")
            for n in _cli_names():
                paths.append(os.path.join(macos, n))
        for root in ("/usr/local/bin", "/opt/homebrew/bin", os.path.join(home, "bin")):
            for n in _cli_names():
                paths.append(os.path.join(root, n))
    else:
        roots = [
            "/usr/bin",
            "/usr/local/bin",
            os.path.join(home, ".local", "bin"),
            "/opt/solidcraft",
            "/opt/SolidCraft",
            "/opt/solidcraft/bin",
            "/snap/bin",
            "/snap/solidcraft/current/bin",
            "/snap/solidcraft/current/usr/bin",
        ]
        for root in roots:
            for n in _cli_names():
                paths.append(os.path.join(root, n))
        paths += _cli_in_named_trees("/opt")
    return paths

def _extracted_cli_paths():
    """Portable zips, Linux tar.gz trees, and an already-extracted AppImage."""
    home = HOME
    bases = [
        home,
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Applications"),
        "/opt",
        APP_DIR,
    ]
    paths = []
    for base in bases:
        paths += _cli_in_named_trees(base)
        if not base or not os.path.isdir(base):
            continue
        for n in _cli_names():
            paths.append(os.path.join(base, n))
        # AppImage --appimage-extract writes squashfs-root (name does not contain SolidCraft).
        extract_roots = [os.path.join(base, "squashfs-root")]
        try:
            for ent in os.listdir(base):
                extract_roots.append(os.path.join(base, ent, "squashfs-root"))
        except OSError:
            pass
        for root in extract_roots:
            if not os.path.isdir(root):
                continue
            for rel in (("usr", "bin"), ("bin",), ("",)):
                for n in _cli_names():
                    paths.append(os.path.join(root, *rel, n) if rel != ("",) else os.path.join(root, n))
    return paths

def find_cli(settings=None):
    """Locate solidcraft-cli. A path saved in settings wins; otherwise search.

    Order: saved path, next to this app, PATH, per-OS install folders,
    portable / extracted copies, then the older Windows
    Documents\\GrokPrograms\\SolidCraft layout.
    """
    if settings is None:
        settings = load_settings()
    configured = (settings.get("cli_path") or "").strip().strip('"')
    if configured and os.path.isfile(configured):
        return os.path.abspath(configured)

    hit = _best_existing(_beside_app_paths())
    if hit:
        return hit

    for n in _cli_names():
        w = shutil.which(n)
        if w and os.path.isfile(w):
            return os.path.abspath(w)

    hit = _best_existing(_install_paths())
    if hit:
        return hit

    hit = _best_existing(_extracted_cli_paths())
    if hit:
        return hit

    old = [
        os.path.join(_OLD_CLI_ROOT, "solidcraft-0.18.3-windows-x64-portable", "solidcraft-cli.exe"),
        os.path.join(_OLD_CLI_ROOT, "solidcraft-cli.exe"),
        os.path.join(_OLD_CLI_ROOT, "solidcraft-cli"),
    ]
    old += _cli_in_named_trees(_OLD_CLI_ROOT)
    hit = _best_existing(old)
    if hit:
        return hit
    raise FileNotFoundError(CLI_MISSING_MSG)

# ---------------------------------------------------------------- fonts
_FONT_EXT = (".ttf", ".otf", ".ttc", ".otc")

def _walk_font_dirs(roots):
    out = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirnames, names in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for n in names:
                if n.lower().endswith(_FONT_EXT):
                    out.append(os.path.join(dirpath, n))
    return out

def _fonts_from_fc_list():
    """Linux fontconfig. Returns [] when fc-list is missing or fails."""
    try:
        kwargs = dict(capture_output=True, timeout=60)
        r = subprocess.run(["fc-list", "-f", "%{file}\n"], **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []
    text = (r.stdout or b"").decode("utf-8", "replace")
    out, seen = [], set()
    for line in text.splitlines():
        p = line.strip().split(":", 1)[0].strip()
        if not p.lower().endswith(_FONT_EXT) or not os.path.isfile(p):
            continue
        key = os.path.normcase(os.path.abspath(p))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out

def _installed_font_files():
    """Fonts installed for this OS. Extra files are added by list_fonts."""
    if os.name == "nt":
        files = _font_dirs_from_registry()
        if not files:
            windir = os.environ.get("WINDIR", r"C:\Windows")
            files = _walk_font_dirs([os.path.join(windir, "Fonts")])
        return files
    if sys.platform == "darwin":
        return _walk_font_dirs([
            "/System/Library/Fonts",
            "/Library/Fonts",
            os.path.join(HOME, "Library", "Fonts"),
        ])
    files = _fonts_from_fc_list()
    if files:
        return files
    return _walk_font_dirs([
        "/usr/share/fonts",
        os.path.join(HOME, ".local", "share", "fonts"),
        os.path.join(HOME, ".fonts"),
    ])

def _font_dirs_from_registry():
    out = []
    if os.name != "nt":
        return out
    import winreg
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            k = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        except OSError:
            continue
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(k, i)
            except OSError:
                break
            i += 1
            if not isinstance(val, str):
                continue
            p = val if os.path.isabs(val) else os.path.join(windir, "Fonts", val)
            if p.lower().endswith((".ttf", ".otf", ".ttc")) and os.path.exists(p):
                out.append(p)
    return out

def _read_names(path):
    from fontTools.ttLib import TTFont, TTCollection
    res = []
    if path.lower().endswith(".ttc"):
        coll = TTCollection(path, lazy=True)
        fonts = list(enumerate(coll.fonts))
    else:
        fonts = [(0, TTFont(path, lazy=True, fontNumber=0))]
    for idx, t in fonts:
        n = t["name"]
        fam = str(n.getDebugName(16) or n.getDebugName(1) or "")
        sub = str(n.getDebugName(17) or n.getDebugName(2) or "Regular")
        full = str(n.getDebugName(4) or (fam + " " + sub))
        try:
            weight = t["OS/2"].usWeightClass
            italic = bool(t["OS/2"].fsSelection & 1)
        except Exception:
            weight, italic = 400, False
        try:
            cmap = t.getBestCmap() or {}
            has_ext = all(ord(c) in cmap for c in "óáéíú")
        except Exception:
            has_ext = True
        res.append({"name": full, "family": fam, "style": sub, "path": path, "index": idx,
                    "weight": weight, "italic": italic, "latin": has_ext})
    return res

def list_fonts(refresh=False, extra_files=()):
    """Return a list of font dicts: name (friendly), family, style, path, index, weight, italic."""
    cache = {}
    if not refresh:
        try:
            with open(FONT_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    files = _installed_font_files()
    files += [p for p in extra_files if os.path.exists(p)]
    seen, fonts, newcache = set(), [], {}
    for p in files:
        key = os.path.normcase(p)
        if key in seen:
            continue
        seen.add(key)
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        ent = cache.get(key)
        if ent and ent.get("mtime") == mt:
            items = ent["fonts"]
        else:
            try:
                items = _read_names(p)
            except Exception:
                items = []
        newcache[key] = {"mtime": mt, "fonts": items}
        for it in items:
            fonts.append(dict(it))
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(FONT_CACHE, "w", encoding="utf-8") as f:
            json.dump(newcache, f)
    except Exception:
        pass
    # unique names
    out, names = [], set()
    for ft in sorted(fonts, key=lambda d: d["name"].lower()):
        if ft["name"] in names:
            continue
        names.add(ft["name"])
        out.append(ft)
    return out

def font_from_file(path):
    items = _read_names(path)
    it = items[0]
    it["name"] = it["name"] + "  [" + os.path.basename(path) + "]"
    return it

# A common serif, in the order Sign Maker tries them. The first one installed wins.
SERIF_FONT_NAMES = (
    "Times New Roman",
    "Liberation Serif",
    "DejaVu Serif",
    "Times",
    "Nimbus Roman",
    "Georgia",
)
SANS_FONT_NAMES = (
    "Arial",
    "Helvetica",
    "Liberation Sans",
    "DejaVu Sans",
    "Nimbus Sans",
)

def match_font(fonts, names):
    """A listed font whose name equals one of names, or contains that name."""
    by_exact = {}
    for f in fonts:
        by_exact.setdefault(f["name"].lower(), f)
    for name in names:
        hit = by_exact.get(name.lower())
        if hit:
            return hit
    wants = [n.lower() for n in names]
    for want in wants:
        for f in fonts:
            if want in f["name"].lower():
                return f
    return None

def preferred_font_name(fonts, names=None):
    """Times New Roman when it is installed, otherwise another common serif, otherwise the first font."""
    if names is None:
        names = SERIF_FONT_NAMES
    hit = match_font(fonts, names)
    if hit:
        return hit["name"]
    return fonts[0]["name"] if fonts else ""

def bold_variant(font, fonts):
    """The bold face of the same family, or None."""
    if font.get("weight", 400) >= 700:
        return font
    best = None
    for f in fonts:
        if f["family"] == font["family"] and f.get("italic") == font.get("italic") and f.get("weight", 400) >= 700:
            if best is None or abs(f["weight"] - 700) < abs(best["weight"] - 700):
                best = f
    return best

def missing_glyphs(font, text):
    try:
        from fontTools.ttLib import TTFont
        t = TTFont(font["path"], lazy=True, fontNumber=font.get("index", 0))
        cmap = t.getBestCmap() or {}
        return sorted({c for c in text if not c.isspace() and ord(c) not in cmap})
    except Exception:
        return []

def sc_font_arg(font):
    """What to hand SolidCraft's sketch.text font: a file path (or full name for .ttc collections)."""
    if font["path"].lower().endswith(".ttc"):
        return font["name"]
    return font["path"]

# ---------------------------------------------------------------- 2D preview
_CAP = {}
def cap_ratio(font):
    """Capital height / em from the font's OS/2 table (what SolidCraft's text height means)."""
    key = (font["path"], font.get("index", 0))
    if key not in _CAP:
        try:
            from fontTools.ttLib import TTFont
            t = TTFont(font["path"], lazy=True, fontNumber=font.get("index", 0))
            ch = getattr(t["OS/2"], "sCapHeight", 0) or 0
            _CAP[key] = ch / t["head"].unitsPerEm if ch > 0 else None
        except Exception:
            _CAP[key] = None
    return _CAP[key]

def snapshot_background_mask(im):
    """Find the backdrop of a SolidCraft snapshot (a plain top-to-bottom gradient).
    Returns an "L" mask: 255 where the pixel is backdrop, 0 on the sign, soft on the edges.
    Only backdrop joined to the picture's corners counts, so a plate colour that happens to
    match the gradient is left alone."""
    from PIL import Image, ImageChops, ImageDraw
    im = im.convert("RGB")
    W, H = im.size
    back = im.crop((0, 0, 1, H)).resize((W, H), Image.Resampling.NEAREST)
    r, g, b = ImageChops.difference(im, back).split()
    d = ImageChops.lighter(ImageChops.lighter(r, g), b)
    lo, hi = 3, 24
    hard = d.point(lambda v: 255 if v <= hi else 0)
    for xy in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
        if hard.getpixel(xy) == 255:
            ImageDraw.floodfill(hard, xy, 128)
    joined = hard.point(lambda v: 255 if v == 128 else 0)
    soft = d.point(lambda v: 255 if v <= lo else (0 if v >= hi else int(255 * (hi - v) / (hi - lo))))
    return ImageChops.multiply(soft, joined)


def recolour_snapshot(im, mask, colour):
    """Put a snapshot on a new backdrop: a soft vertical gradient around colour (#rrggbb or RGB)."""
    from PIL import Image
    if isinstance(colour, str):
        colour = tuple(int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    top = tuple(min(255, c + 14) for c in colour)
    bottom = tuple(max(0, c - 8) for c in colour)
    W, H = im.size
    grad = Image.linear_gradient("L").resize((W, H))
    back = Image.composite(Image.new("RGB", (W, H), bottom), Image.new("RGB", (W, H), top), grad)
    return Image.composite(back, im.convert("RGB"), mask)


def preview_image(p, font, width_px=760, bg=(236, 236, 236)):
    """Draw the sign at true proportions using the real font file. Returns (PIL image, info dict)."""
    from PIL import Image, ImageDraw, ImageFont
    L, H, m = float(p["length"]), float(p["height"]), float(p["margin"])
    pad = 30
    scale = (width_px - 2 * pad) / L
    W, Hh = width_px, int(H * scale + 2 * pad)
    img = Image.new("RGB", (W, Hh), bg)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = pad, pad, pad + L * scale, pad + H * scale
    r = min(float(p.get("corner", 0) or 0), H / 2 - 0.01, L / 2 - 0.01) * scale
    d.rounded_rectangle([x0 + 3, y0 + 4, x1 + 3, y1 + 4], radius=max(r, 0), fill=(200, 200, 200))
    d.rounded_rectangle([x0, y0, x1, y1], radius=max(r, 0), fill=p["plate_color"], outline=(120, 120, 120))
    # margin box (dotted)
    mx0, my0, mx1, my1 = x0 + m * scale, y0 + m * scale, x1 - m * scale, y1 - m * scale
    for xx in range(int(mx0), int(mx1), 8):
        d.line([xx, my0, xx + 3, my0], fill=(170, 170, 170)); d.line([xx, my1, xx + 3, my1], fill=(170, 170, 170))
    for yy in range(int(my0), int(my1), 8):
        d.line([mx0, yy, mx0, yy + 3], fill=(170, 170, 170)); d.line([mx1, yy, mx1, yy + 3], fill=(170, 170, 170))
    text = p["text"]
    info = {"ok": True}
    if not text.strip():
        info["ok"] = False
        return img, info
    base = 400  # render big then scale
    f = ImageFont.truetype(font["path"], base, index=font.get("index", 0))
    cr = cap_ratio(font)
    if cr:
        cap_px = base * cr
    else:
        hb = f.getbbox("H")
        cap_px = hb[3] - hb[1]
    spacing_px = float(p.get("spacing", 0) or 0)  # mm, converted after scale known
    def render(spx):
        if spx == 0:
            bb = f.getbbox(text)
            im = Image.new("L", (bb[2] - bb[0] + 4, bb[3] - bb[1] + 4), 0)
            ImageDraw.Draw(im).text((-bb[0] + 2, -bb[1] + 2), text, font=f, fill=255)
            return im
        widths = [f.getlength(c) for c in text]
        tot = int(sum(widths) + spx * max(len(text) - 1, 0) + base)
        im = Image.new("L", (max(tot, 10), base * 2), 0)
        dd = ImageDraw.Draw(im); x = base // 4
        for c, w in zip(text, widths):
            dd.text((x, base // 2), c, font=f, fill=255); x += w + spx
        bb = im.getbbox() or (0, 0, 1, 1)
        return im.crop(bb)
    mask = render(0)
    bb = mask.getbbox() or (0, 0, 1, 1)
    w_px, h_px = bb[2] - bb[0], bb[3] - bb[1]
    if p.get("auto_size", True):
        k = min((L - 2 * m) / (w_px / cap_px), (H - 2 * m) / (h_px / cap_px))  # cap height mm
        if spacing_px:
            for _ in range(4):
                mask = render(spacing_px * cap_px / k)
                bbm = mask.getbbox() or (0, 0, 1, 1)
                k = min((L - 2 * m) / ((bbm[2] - bbm[0]) / cap_px), (H - 2 * m) / ((bbm[3] - bbm[1]) / cap_px))
    else:
        k = float(p["text_size"])
    if spacing_px:
        mask = render(spacing_px * cap_px / k)
    mask = mask.crop(mask.getbbox() or (0, 0, 1, 1))
    mm_per_px = k / cap_px
    tw_mm, th_mm = mask.width * mm_per_px, mask.height * mm_per_px
    sw, sh = max(1, int(round(tw_mm * scale))), max(1, int(round(th_mm * scale)))
    mask = mask.resize((sw, sh), Image.LANCZOS)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    col = Image.new("RGB", (sw, sh), p["text_color"])
    if p.get("style") == "engraved":
        shade = Image.new("RGB", (sw, sh), (90, 90, 90))
        img.paste(shade, (int(cx - sw / 2) + 1, int(cy - sh / 2) - 1), mask)
    else:
        shade = Image.new("RGB", (sw, sh), (60, 60, 60))
        img.paste(shade, (int(cx - sw / 2) + 2, int(cy - sh / 2) + 2), mask)
    img.paste(col, (int(cx - sw / 2), int(cy - sh / 2)), mask)
    info.update(cap_mm=k, text_w=tw_mm, text_h=th_mm,
                fits=(tw_mm <= L - 2 * m + 0.01 and th_mm <= H - 2 * m + 0.01))
    return img, info

# ---------------------------------------------------------------- SolidCraft
class Cancelled(Exception):
    """A build was cancelled because a newer one replaced it."""


def _run(args, timeout=600, cancel=None):
    """Run solidcraft-cli. cancel: a threading.Event; when it is set the process is killed."""
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    # CREATE_NO_WINDOW is Windows-only. Passing creationflags elsewhere raises.
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    proc = subprocess.Popen(args, **kwargs)
    deadline = time.monotonic() + timeout
    while True:
        try:
            so, se = proc.communicate(timeout=0.2)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                proc.kill(); proc.communicate()
                raise Cancelled()
            if time.monotonic() > deadline:
                proc.kill(); proc.communicate()
                raise subprocess.TimeoutExpired(args, timeout)
    out = (so or b"").decode("utf-8", "replace") + (se or b"").decode("utf-8", "replace")
    return proc.returncode, out

def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=True, indent=1)

def _cmd(c, **params):
    return {"command": c, "params": params}

def build_commands(p, font, cap, at, glyph_names=None, plate=True, export=None):
    L, H, T = float(p["length"]), float(p["height"]), float(p["thickness"])
    depth = float(p["raise"])
    engraved = p.get("style") == "engraved"
    if engraved:
        depth = min(depth, T - 0.2)
    cmds = []
    if plate:
        cmds.append(_cmd("sketch.create", plane="XY", name="PlateSketch"))
        r = float(p.get("corner", 0) or 0)
        if r > 0:
            r = min(r, H / 2 - 0.05, L / 2 - 0.05)
            cmds.append(_cmd("sketch.rectangle.rounded", p0=[-L / 2, -H / 2], p1=[L / 2, H / 2], radius=r))
        else:
            cmds.append(_cmd("sketch.rectangle.center", center=[0, 0], corner=[L / 2, H / 2]))
        cmds.append(_cmd("sketch.finish"))
        cmds.append(_cmd("solid.extrude", distance=T, body_name="Plate", operation="new", name="Plate"))
    cmds.append(_cmd("sketch.create", plane="XY", offset=T, name="TextSketch"))
    tp = dict(text=p["text"], at=[round(at[0], 4), round(at[1], 4)], height=round(cap, 4),
              font=sc_font_arg(font), align="center")
    if float(p.get("spacing", 0) or 0):
        tp["letter_spacing"] = float(p["spacing"])
    cmds.append(_cmd("sketch.text", **tp))
    cmds.append(_cmd("sketch.finish"))
    if engraved:
        cmds.append(_cmd("solid.extrude", distance=depth, direction="negative", body_name="Text", operation="new", name="Text"))
    else:
        cmds.append(_cmd("solid.extrude", distance=depth, body_name="Text", operation="new", name="Text"))
    if glyph_names:
        tools = [n for n in glyph_names if n != "Text"]
        if tools:
            cmds.append(_cmd("solid.combine", target="Text", tools=tools, operation="join"))
        if engraved and plate:
            cmds.append(_cmd("solid.combine", target="Plate", tools=["Text"], operation="cut", keep_tools=True))
    if plate:
        cmds.append(_cmd("appearance.assign", bodies=["Plate"], color=p["plate_color"]))
    cmds.append(_cmd("appearance.assign", bodies=["Text"], color=p["text_color"]))
    if export:
        for path, fmt, bodies in export:
            cmds.append(_cmd("file.export", path=path, format=fmt, bodies=bodies))
    return {"commands": cmds}

def _eval(cli, design, work, cancel=None):
    jo = os.path.join(work, "eval.json")
    if os.path.exists(jo):
        os.remove(jo)
    rc, out = _run([cli, "eval", design, "--json-out", jo], cancel=cancel)
    if rc != 0 or not os.path.exists(jo):
        raise RuntimeError("SolidCraft eval failed:\n" + out[-2000:])
    with open(jo, encoding="utf-8") as f:
        return json.load(f)

def _text_bodies(ev):
    return [b for b in ev["bodies"] if b["name"] == "Text" or b["name"].startswith("Text (")]

def _union_bbox(bodies):
    mn = [min(b["bbox"]["min"][i] for b in bodies) for i in range(3)]
    mx = [max(b["bbox"]["max"][i] for b in bodies) for i in range(3)]
    return mn, mx

def new_work_dir(prefix=""):
    """A fresh, unique folder under WORK_DIR (two builds in the same second never share one)."""
    os.makedirs(WORK_DIR, exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix + time.strftime("%Y%m%d-%H%M%S-"), dir=WORK_DIR)

def build_sign(p, font, work=None, log=print, want_snapshot=True, final_exports=True, cancel=None):
    """Build headless. Returns dict with design, 3mf, stls, snapshot, eval, bboxes, cap height.
    cancel: optional threading.Event. Setting it stops the build and raises Cancelled."""
    cli = find_cli()
    work = work or new_work_dir()
    os.makedirs(work, exist_ok=True)
    L, H, T, m = float(p["length"]), float(p["height"]), float(p["thickness"]), float(p["margin"])
    aw, ah = L - 2 * m, H - 2 * m
    if not p["text"].strip():
        raise ValueError("Type some wording first.")
    # pass 1: measure the text at a known size
    cap0 = 10.0
    s1 = os.path.join(work, "measure.json")
    _write_json(s1, build_commands(p, font, cap0, (0, 0), plate=False))
    d1 = os.path.join(work, "measure.solidcraft")
    log("Measuring the text in SolidCraft…")
    rc, out = _run([cli, "run", s1, "--save", d1, "--quiet"], cancel=cancel)
    if rc != 0:
        raise RuntimeError("SolidCraft could not set this text in this font:\n" + out[-1500:])
    ev = _eval(cli, d1, work, cancel)
    tb = _text_bodies(ev)
    if not tb:
        raise RuntimeError("SolidCraft made no text bodies (the font may have no outlines for this wording).")
    names = [b["name"] for b in tb]
    mn, mx = _union_bbox(tb)
    w, h = mx[0] - mn[0], mx[1] - mn[1]
    cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
    if p.get("auto_size", True):
        k = min(aw / w, ah / h)
        cap = cap0 * k
    else:
        cap = float(p["text_size"]); k = cap / cap0
    at = (-cx * k, -cy * k)
    design = os.path.join(work, "sign.solidcraft")
    f3 = os.path.join(work, "sign_raw.3mf")
    exports = [(f3, "3mf", ["Plate", "Text"])]
    if p.get("stl"):
        exports += [(os.path.join(work, "plate.stl"), "stl", ["Plate"]), (os.path.join(work, "text.stl"), "stl", ["Text"])]
    def probe_names():
        """The text bodies SolidCraft makes at this exact size and position, before they are joined.
        Script fonts (Lobster etc.) have overlapping, joined-up letters, and the number of separate
        outlines can change with the size, so names measured at the first size may not match."""
        sp = os.path.join(work, "probe.json")
        _write_json(sp, build_commands(p, font, cap, at, plate=False))
        dp = os.path.join(work, "probe.solidcraft")
        rc, out = _run([cli, "run", sp, "--save", dp, "--quiet"], cancel=cancel)
        if rc != 0:
            raise RuntimeError("SolidCraft build failed:\n" + out[-1500:])
        return [b["name"] for b in _text_bodies(_eval(cli, dp, work, cancel))]

    best = None          # (off-centre error, cap, at, names) of the best single-body build so far
    tries = 0
    while True:
        tries += 1
        s2 = os.path.join(work, "build.json")
        _write_json(s2, build_commands(p, font, cap, at, glyph_names=names, export=exports))
        log("Building the sign in SolidCraft (pass %d)…" % tries)
        rc, out = _run([cli, "run", s2, "--save", design, "--quiet"], cancel=cancel)
        if rc != 0:
            raise RuntimeError("SolidCraft build failed:\n" + out[-1500:])
        ev = _eval(cli, design, work, cancel)
        tb = _text_bodies(ev)
        if len(tb) != 1:
            # The letters split into different pieces at this size: ask SolidCraft for the real names.
            if tries >= 6:
                raise RuntimeError("SolidCraft could not join the letters of this wording into one piece.")
            names = probe_names()
            continue
        mn, mx = _union_bbox(tb)
        w, h = mx[0] - mn[0], mx[1] - mn[1]
        cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
        fit = min(aw / w, ah / h) if p.get("auto_size", True) else 1.0
        err = max(abs(cx), abs(cy), abs(fit - 1.0) * max(aw, ah))
        if abs(cx) < 0.02 and abs(cy) < 0.02 and (fit >= 0.999 and (not p.get("auto_size", True) or fit < 1.01)):
            break
        if best is None or err < best[0]:
            best = (err, cap, at, names)
        if tries >= 6:
            # Close enough for printing (within 0.1 mm): rebuild the best try instead of failing.
            if best[0] <= 0.1:
                _, cap, at, names = best
                _write_json(s2, build_commands(p, font, cap, at, glyph_names=names, export=exports))
                rc, out = _run([cli, "run", s2, "--save", design, "--quiet"], cancel=cancel)
                ev = _eval(cli, design, work, cancel) if rc == 0 else None
                if ev is not None and len(_text_bodies(ev)) == 1:
                    tb = _text_bodies(ev)
                    break
            raise RuntimeError("Could not centre the text after several tries.")
        if not p.get("auto_size", True):
            fit = 1.0
        cap *= fit
        at = ((at[0] - cx) * fit, (at[1] - cy) * fit)
    plate = [b for b in ev["bodies"] if b["name"] == "Plate"]
    others = [b["name"] for b in ev["bodies"] if b["name"] not in ("Plate", "Text")]
    res = {"work": work, "design": design, "raw3mf": f3, "cap": cap, "eval": ev,
           "plate_bbox": plate[0]["bbox"] if plate else None, "text_bbox": tb[0]["bbox"],
           "extra_bodies": others, "font": font}
    res["3mf"] = os.path.join(work, "sign.3mf")
    make_multipart_3mf(f3, res["3mf"], p)
    if p.get("stl"):
        res["stls"] = [os.path.join(work, "plate.stl"), os.path.join(work, "text.stl")]
    if want_snapshot:
        snap = os.path.join(work, "preview.png")
        log("Rendering 3D preview…")
        cam = {"target": [0, 0, 0.5], "yaw": -0.5, "pitch": 0.75, "distance": max(L * 0.95, H * 2.5)}
        rc, out = _run([cli, "snapshot", design, "--out", snap, "--no-grid", "--no-axes", "--width", "1200", "--height", "700",
                        "--camera", json.dumps(cam)], cancel=cancel)
        res["snapshot"] = snap if rc == 0 and os.path.exists(snap) else None
    return res

# ---------------------------------------------------------------- 3MF
def make_multipart_3mf(src, dst, p):
    """Rewrite SolidCraft's 3MF (two separate build items) as ONE object with two parts
    (Plate + Text) so Bambu Studio / OrcaSlicer / Anycubic Slicer Next load it as a single
    multi-part object; keeps coordinates so the text sits exactly on the plate."""
    import xml.etree.ElementTree as ET
    NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ET.register_namespace("", NS)
    with zipfile.ZipFile(src) as z:
        model = z.read("3D/3dmodel.model")
    root = ET.fromstring(model)
    res = root.find("{%s}resources" % NS)
    build = root.find("{%s}build" % NS)
    objs = [o for o in res.findall("{%s}object" % NS) if o.find("{%s}mesh" % NS) is not None]
    byname = {o.get("name"): o for o in objs}
    if "Plate" not in byname or "Text" not in byname:
        raise RuntimeError("3MF export is missing the Plate or Text body")
    ids = [int(o.get("id")) for o in res]
    new_id = max(ids) + 1
    parent = ET.SubElement(res, "{%s}object" % NS, {"id": str(new_id), "type": "model", "name": p["text"]})
    comps = ET.SubElement(parent, "{%s}components" % NS)
    order = [byname["Plate"], byname["Text"]]
    for o in order:
        ET.SubElement(comps, "{%s}component" % NS, {"objectid": o.get("id")})
    for it in list(build):
        build.remove(it)
    ET.SubElement(build, "{%s}item" % NS, {"objectid": str(new_id)})
    meta = root.find("{%s}metadata" % NS)
    for k, v in (("Title", p["text"]), ("Designer", "Del (postmanpat)"), ("Description", "Two-colour sign made with Sign Maker / SolidCraft")):
        e = ET.Element("{%s}metadata" % NS, {"name": k}); e.text = v
        root.insert(0, e)
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    # Bambu/Orca per-part settings: names, part type and filament (extruder 1 = plate, 2 = text)
    parts = ""
    for i, (o, ext) in enumerate(zip(order, (1, 2))):
        parts += ('  <part id="%s" subtype="normal_part">\n    <metadata key="name" value="%s"/>\n'
                  '    <metadata key="extruder" value="%d"/>\n  </part>\n') % (o.get("id"), o.get("name"), ext)
    cfg = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n <object id="%d">\n'
           '  <metadata key="name" value="%s"/>\n  <metadata key="extruder" value="1"/>\n%s </object>\n</config>\n'
           ) % (new_id, _xml_esc(p["text"]), parts)
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "3D/3dmodel.model":
                zout.writestr(item.filename, xml)
            else:
                zout.writestr(item, zin.read(item.filename))
        zout.writestr("Metadata/model_settings.config", cfg)
    return dst

def _xml_esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def inspect_3mf(path):
    import xml.etree.ElementTree as ET
    NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
        names = z.namelist()
    out = {"files": names, "objects": [], "build": []}
    for o in root.find(NS + "resources").findall(NS + "object"):
        mesh = o.find(NS + "mesh")
        d = {"id": o.get("id"), "name": o.get("name")}
        if mesh is not None:
            vs = [(float(v.get("x")), float(v.get("y")), float(v.get("z"))) for v in mesh.iter(NS + "vertex")]
            d["vertices"] = len(vs); d["triangles"] = len(list(mesh.iter(NS + "triangle")))
            d["bbox"] = [[round(min(v[i] for v in vs), 3) for i in range(3)], [round(max(v[i] for v in vs), 3) for i in range(3)]]
        comps = o.find(NS + "components")
        if comps is not None:
            d["components"] = [c.get("objectid") for c in comps]
        out["objects"].append(d)
    out["build"] = [i.get("objectid") for i in root.find(NS + "build")]
    return out

# ---------------------------------------------------------------- dimension picture
def _cam_basis(yaw, pitch):
    e = (-math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), math.sin(pitch))
    f = tuple(-c for c in e)
    up = (0, 0, 1)
    r = (f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0])
    n = math.sqrt(sum(c * c for c in r)); r = tuple(c / n for c in r)
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    return r, u

def dimension_png(res, p, out_png, log=print):
    """Ortho 3/4 view rendered by SolidCraft, annotated with dimension lines (projected exactly)."""
    from PIL import Image, ImageDraw, ImageFont
    cli = find_cli()
    L, H, T = float(p["length"]), float(p["height"]), float(p["thickness"])
    tb = res["text_bbox"]; tmin, tmax = tb["min"], tb["max"]
    top = max(tmax[2], T)
    W, Hp = 1600, 1000
    yaw, pitch = -0.42, 0.62
    dist = L * 1.3
    target = [-L * 0.03, -H * 0.1, 0.0]
    cam = {"target": target, "yaw": yaw, "pitch": pitch, "distance": dist}
    raw = os.path.join(res["work"], "dims_raw.png")
    rc, out = _run([cli, "snapshot", res["design"], "--out", raw, "--no-grid", "--no-axes",
                    "--width", str(W), "--height", str(Hp), "--camera", json.dumps(cam)])
    if rc != 0:
        raise RuntimeError("snapshot failed: " + out[-800:])
    im = Image.open(raw).convert("RGB")
    W, Hp = im.size
    r, u = _cam_basis(yaw, pitch)
    hh = 0.4 * dist
    def P(x, y, z):
        v = (x - target[0], y - target[1], z - target[2])
        sx = sum(a * b for a, b in zip(v, r)); sy = sum(a * b for a, b in zip(v, u))
        return (W / 2 + sx / hh * (Hp / 2), Hp / 2 - sy / hh * (Hp / 2))
    d = ImageDraw.Draw(im)
    def ft(sz, bold=False):
        for n in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(n, sz)
            except Exception:
                pass
        return ImageFont.load_default()
    f, fs = ft(26, True), ft(22)
    col = (30, 60, 140)
    def arrow(a, b):
        d.line([a, b], fill=col, width=3)
        for p1, q in ((a, b), (b, a)):
            ang = math.atan2(q[1] - p1[1], q[0] - p1[0])
            for s in (0.38, -0.38):
                d.line([p1, (p1[0] + 16 * math.cos(ang + s), p1[1] + 16 * math.sin(ang + s))], fill=col, width=3)
    def label(txt, c):
        bb = d.textbbox((0, 0), txt, font=f); w = bb[2] - bb[0]; h = bb[3] - bb[1]
        x, y = c[0] - w / 2, c[1] - h / 2
        d.rectangle([x - 8, y - 7, x + w + 8, y + h + 9], fill=(255, 255, 255), outline=col, width=2)
        d.text((x - bb[0], y - bb[1]), txt, font=f, fill=col)
    def dim3(a, b, off, txt, lab_shift=(0, 0)):
        a2 = tuple(a[i] + off[i] for i in range(3)); b2 = tuple(b[i] + off[i] for i in range(3))
        ext = tuple(off[i] * 1.15 for i in range(3))
        d.line([P(*a), P(a[0] + ext[0], a[1] + ext[1], a[2] + ext[2])], fill=col, width=1)
        d.line([P(*b), P(b[0] + ext[0], b[1] + ext[1], b[2] + ext[2])], fill=col, width=1)
        A, B = P(*a2), P(*b2); arrow(A, B)
        label(txt, ((A[0] + B[0]) / 2 + lab_shift[0], (A[1] + B[1]) / 2 + lab_shift[1]))
    fmt = lambda v: ("%.2f" % v).rstrip("0").rstrip(".")
    # plate length along front edge
    dim3((-L / 2, -H / 2, 0), (L / 2, -H / 2, 0), (0, -H * 0.45, 0), fmt(L) + " mm")
    # plate depth along right edge
    dim3((L / 2, -H / 2, 0), (L / 2, H / 2, 0), (L * 0.07, 0, 0), fmt(H) + " mm", (60, 0))
    # thickness + text raise at left front corner (vertical)
    x = -L / 2; y = -H / 2
    a, b = P(x, y, 0), P(x, y, T)
    ox = -70
    d.line([a, (a[0] + ox - 10, a[1])], fill=col, width=1); d.line([b, (b[0] + ox - 10, b[1])], fill=col, width=1)
    d.line([(a[0] + ox, a[1]), (b[0] + ox, b[1])], fill=col, width=3)
    label("plate " + fmt(T) + " mm", (a[0] + ox - 110, (a[1] + b[1]) / 2))
    # text width along top of text
    tz = top
    dim3((tmin[0], tmax[1], tz), (tmax[0], tmax[1], tz), (0, H * 0.55, 0), "text " + fmt(tmax[0] - tmin[0]) + " mm")
    # info box
    style = "engraved %s mm" % fmt(T - tmin[2]) if p.get("style") == "engraved" else "raised %s mm" % fmt(tmax[2] - T)
    lines = [p["text"].upper() if False else p["text"],
             "Overall: %s x %s x %s mm" % (fmt(L), fmt(H), fmt(top)),
             "Plate: %s x %s x %s mm, %s" % (fmt(L), fmt(H), fmt(T), p["plate_color"]),
             "Text: %s x %s mm, %s, %s" % (fmt(tmax[0] - tmin[0]), fmt(tmax[1] - tmin[1]), style, p["text_color"]),
             "Font: %s, cap height %s mm" % (res["font"]["name"], fmt(res["cap"])),
             "Margin %s mm%s" % (fmt(float(p["margin"])), (", corners R%s" % fmt(float(p["corner"]))) if float(p.get("corner", 0) or 0) > 0 else "")]
    tf = ft(30, True)
    x0, y0 = 30, 24
    widths = [d.textbbox((0, 0), t, font=(tf if i == 0 else fs))[2] for i, t in enumerate(lines)]
    d.rectangle([x0 - 12, y0 - 12, x0 + max(widths) + 14, y0 + 40 + 30 * (len(lines) - 1) + 10], fill=(255, 255, 255), outline=col, width=2)
    try:
        tff = ImageFont.truetype(res["font"]["path"], 34, index=res["font"].get("index", 0))
    except Exception:
        tff = tf
    d.text((x0, y0), lines[0], font=tff, fill=col)
    for i, t in enumerate(lines[1:]):
        d.text((x0, y0 + 44 + 30 * i), t, font=fs, fill=col)
    im.save(out_png)
    return out_png

# ---------------------------------------------------------------- output folder
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
def safe_name(text):
    s = _BAD.sub("", text.replace("\n", " ")).strip().rstrip(". ")
    s = re.sub(r"\s+", " ", s)
    if s.upper() in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?i)(COM|LPT)\d", s or ""):
        s = "_" + s
    return s[:60] or "Sign"

def save_outputs(res, p, root=None, log=print):
    if root is None:
        root = output_root()
    name = safe_name(p["text"])
    folder = os.path.join(root, name)
    os.makedirs(folder, exist_ok=True)
    base, n = name, 1
    def taken(b):
        return any(os.path.exists(os.path.join(folder, b + ext)) for ext in (".solidcraft", ".3mf", " - dimensions.png"))
    while taken(base):
        n += 1; base = "%s_v%d" % (name, n)
    out = {"folder": folder, "base": base}
    shutil.copy2(res["design"], os.path.join(folder, base + ".solidcraft")); out["design"] = os.path.join(folder, base + ".solidcraft")
    shutil.copy2(res["3mf"], os.path.join(folder, base + ".3mf")); out["3mf"] = os.path.join(folder, base + ".3mf")
    if res.get("stls"):
        for s, tag in zip(res["stls"], ("plate", "text")):
            shutil.copy2(s, os.path.join(folder, "%s - %s.stl" % (base, tag)))
    log("Drawing the dimensions picture…")
    png = os.path.join(res["work"], "dims.png")
    dimension_png(res, p, png)
    shutil.copy2(png, os.path.join(folder, base + " - dimensions.png")); out["png"] = os.path.join(folder, base + " - dimensions.png")
    return out

# ---------------------------------------------------------------- command line (tests)
def _find_font(fonts, want):
    for f in fonts:
        if f["name"].lower() == want.lower():
            return f
    for f in fonts:
        if os.path.normcase(f["path"]) == os.path.normcase(want):
            return f
    if os.path.exists(want):
        return font_from_file(want)
    raise SystemExit("font not found: " + want)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Sign Maker headless build")
    ap.add_argument("text"); ap.add_argument("--font", required=True)
    ap.add_argument("--root", default="", help="folder for saved signs (default: Documents\\Sign Maker\\Signs)")
    ap.add_argument("--style", default="raised"); ap.add_argument("--corner", type=float, default=0)
    ap.add_argument("--plate", default="#FFFFFF"); ap.add_argument("--textcol", default="#000000")
    ap.add_argument("--no-save", action="store_true"); ap.add_argument("--size", type=float, default=0)
    a = ap.parse_args()
    p = json.loads(json.dumps(DEFAULTS)); p.update(text=a.text, style=a.style, corner=a.corner, plate_color=a.plate, text_color=a.textcol)
    if a.size:
        p.update(auto_size=False, text_size=a.size)
    fonts = list_fonts()
    font = _find_font(fonts, a.font)
    print("font:", font["name"], font["path"], "missing:", missing_glyphs(font, a.text))
    res = build_sign(p, font)
    print(json.dumps({"cap": res["cap"], "plate": res["plate_bbox"], "text": res["text_bbox"], "extra": res["extra_bodies"],
                      "snapshot": res.get("snapshot"), "work": res["work"]}, ensure_ascii=False, indent=1))
    print(json.dumps(inspect_3mf(res["3mf"]), indent=1))
    if not a.no_save:
        print(json.dumps(save_outputs(res, p, a.root.strip() or output_root()), ensure_ascii=False, indent=1))
