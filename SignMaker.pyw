# -*- coding: utf-8 -*-
"""Sign Maker for SolidCraft - two-colour 3D-print signs. Author: Del (postmanpat)."""
import os, sys, threading, queue, traceback, subprocess, json, shutil, webbrowser, types, time, math
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, colorchooser, messagebox
from PIL import Image, ImageDraw, ImageFilter, ImageTk
import signcore as sc
try:
    import sv_ttk  # Sun Valley ttk theme (MIT), bundled with the app
except Exception:  # pragma: no cover - the app still runs on plain ttk
    sv_ttk = None

__version__ = "1.1.5"

APP_NAME = "Sign Maker for SolidCraft"
AUTHOR = "Del (postmanpat)"
AUTHOR_URL = "https://github.com/postmanpat-303"
REPO_URL = "https://github.com/postmanpat-303/SignMaker-for-SolidCraft"
RELEASES_URL = REPO_URL + "/releases"
LATEST_API = "https://api.github.com/repos/postmanpat-303/SignMaker-for-SolidCraft/releases/latest"
LICENSE_URL = REPO_URL + "/blob/main/LICENSE"
DONATE_URL = "https://buymeacoffee.com/postmanpat"
PAYPAL_URL = "https://paypal.me/derekh100"
SOLIDCRAFT_URL = "https://github.com/tangency-labs/solidcraft"
SOLIDCRAFT_RELEASES = SOLIDCRAFT_URL + "/releases"

NUM_FIELDS = [("length", "Plate length (mm)"), ("height", "Plate height (mm)"), ("thickness", "Plate thickness (mm)"),
              ("raise", "Text raise / engrave depth (mm)"), ("margin", "Margin (mm)"), ("corner", "Corner radius (mm)"),
              ("spacing", "Extra letter spacing (mm)")]
# Everything that changes the 3D model. Anything else (save folder, STL option...) does not need a new preview.
MODEL_KEYS = ["text", "length", "height", "thickness", "raise", "margin", "corner", "spacing", "auto_size",
              "text_size", "bold", "style", "plate_color", "text_color"]
AUTO_3D_DELAY_MS = 850  # after the 2D preview's own 150 ms: about 1 s after the last change

# Colours that go with the Sun Valley theme. Accent blue matches the app icon.
PALETTE = {
    "light": dict(bg="#fafafa", fg="#1c1c1c", muted="#5f6670", accent="#005fb8", ok="#0f7b0f", warn="#b54708",
                  preview="#eef2f7", preview3d="#e4eaf2", border="#d6dbe1", header="#f0f4fa"),
    "dark": dict(bg="#1c1c1c", fg="#fafafa", muted="#a3a9b1", accent="#57c8ff", ok="#6ccb5f", warn="#f5a524",
                 preview="#262a30", preview3d="#22262c", border="#3a3f46", header="#23272d"),
}

def asset_path(*parts):
    """A file shipped with the app: next to the source, or inside a PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)

def icon_image(size):
    png = asset_path("assets", "icon.png")
    if not os.path.isfile(png):
        return None
    try:
        img = Image.open(png).convert("RGBA")
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None

def apply_window_icon(root):
    """Window and taskbar icon. PNG on every OS; the .ico is also set on Windows."""
    photo = icon_image(256)
    if photo is not None:
        try:
            root.iconphoto(True, photo)
            root._icon_photo = photo
        except Exception:
            pass
    if os.name == "nt":
        ico = asset_path("assets", "icon.ico")
        if os.path.isfile(ico):
            try:
                root.iconbitmap(default=ico)
            except Exception:
                try:
                    root.iconbitmap(ico)
                except Exception:
                    pass

def clear_labels(w):
    """Remove a widget-level -background from ttk labels so their style decides."""
    for ch in w.winfo_children():
        if ch.winfo_class() == "TLabel":
            try:
                ch.configure(background="")
            except tk.TclError:
                pass
        clear_labels(ch)

def open_url(url):
    try:
        webbrowser.open(url, new=2)
    except Exception:
        pass

def version_tuple(v):
    out = []
    for part in str(v).lstrip("vV").split("-")[0].split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    return tuple(out + [0] * (4 - len(out)))

def centre_window(win, parent=None):
    """Place win in the middle of parent (when it is on screen), else in the middle of the screen."""
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    if parent is not None and parent.winfo_viewable():
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x, y = px + (pw - w) // 2, py + (ph - h) // 2
    else:
        x, y = (sw - w) // 2, (sh - h) // 2
    x = max(0, min(x, sw - w)); y = max(0, min(y, sh - h - 40))
    win.geometry("+%d+%d" % (x, y))


def work_area(win):
    """Usable area (x, y, w, h) of the screen the window is on, leaving out the Windows taskbar."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
            u = ctypes.windll.user32
            u.MonitorFromWindow.restype = wintypes.HANDLE
            u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
            hwnd = int(win.wm_frame(), 16) if win.winfo_ismapped() else win.winfo_id()
            mon = u.MonitorFromWindow(hwnd, 2)          # MONITOR_DEFAULTTONEAREST
            mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
            if mon and u.GetMonitorInfoW(mon, ctypes.byref(mi)):
                r = mi.rcWork
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            pass
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            pass
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    return 0, 0, sw, sh - 60


_SCREEN_DPI = None   # measured before the app sets its own tk scaling


def remember_screen_dpi(root):
    global _SCREEN_DPI
    try:
        _SCREEN_DPI = float(root.winfo_fpixels("1i"))
    except Exception:
        _SCREEN_DPI = None


def screen_scale(win):
    """How many screen pixels make one layout pixel (1.0 at 100 %, 1.5 at 150 % display scaling).
    Windows reports 96 dpi to apps it scales itself, so this is 1.0 for them: their sizes are
    already logical pixels."""
    if sys.platform == "darwin":
        return 1.0                                   # Tk already works in points there
    dpi = None
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = int(win.wm_frame(), 16) if win.winfo_ismapped() else win.winfo_id()
            dpi = float(ctypes.windll.user32.GetDpiForWindow(hwnd)) or None
        except Exception:
            dpi = None
    if dpi is None:
        dpi = _SCREEN_DPI
    if not dpi:
        return 1.0
    return max(1.0, min(3.0, dpi / 96.0))


COMPACT_BELOW = 860   # work-area height (layout pixels) under which the compact layout is used


def place_main_window(root, pref_w=1180, pref_h=800):
    """Open the main window centred and fully on screen; maximise when the screen is smaller than the layout."""
    root.update_idletasks()
    ax, ay, aw, ah = work_area(root)
    w = max(pref_w, root.winfo_reqwidth()); h = max(pref_h, root.winfo_reqheight())
    frame_w, frame_h = 16, 40          # window border and title bar
    too_big = w + frame_w > aw or h + frame_h > ah
    w = min(w, aw - frame_w); h = min(h, ah - frame_h)
    root.minsize(min(900, w), min(600, h))
    x = ax + (aw - w - frame_w) // 2; y = ay + (ah - h - frame_h) // 2
    root.geometry("%dx%d+%d+%d" % (w, h, max(ax, x), max(ay, y)))
    root.update_idletasks()              # finish the layout while still hidden
    # Show it once, already at its final size: maximising after showing makes it jump and repaint.
    fade = sys.platform == "win32"
    if fade:
        try:
            root.attributes("-alpha", 0.0)   # first paint happens unseen, so no white flash
        except tk.TclError:
            fade = False
    shown = False
    if too_big:
        try:
            root.state("zoomed")             # Windows / macOS: maps it maximised
            shown = True
        except tk.TclError:
            try:
                root.attributes("-zoomed", True)  # Linux
            except tk.TclError:
                pass
    if not shown:
        root.deiconify()
    root.lift(); root.focus_force()
    if fade:
        root.update_idletasks()
        root.after(40, lambda: root.attributes("-alpha", 1.0))


# ---------------------------------------------------------------- theme
class Theme:
    """Sun Valley (Windows 11 style) light/dark theme with fonts that exist on this OS."""

    def __init__(self, root):
        self.root = root
        self.name = "light"
        self.style = ttk.Style(root)
        self.sv = sv_ttk is not None
        self.compact = False
        fams = {f.lower(): f for f in tkfont.families(root)}

        def pick(*names):
            for n in names:
                if n.lower() in fams:
                    return fams[n.lower()]
            return None

        if os.name == "nt":
            body = pick("Segoe UI Variable Text", "Segoe UI") or "TkDefaultFont"
            strong = pick("Segoe UI Variable Text Semibold", "Segoe UI Semibold")
            display = pick("Segoe UI Variable Display Semibold", "Segoe UI Semibold")
        elif sys.platform == "darwin":
            body = pick("SF Pro Text", ".AppleSystemUIFont", "Helvetica Neue", "Helvetica") or "TkDefaultFont"
            strong = display = None
        else:
            body = pick("Inter", "Noto Sans", "Cantarell", "Ubuntu", "DejaVu Sans", "Liberation Sans") or "TkDefaultFont"
            strong = display = None
        self.family = body
        self.fonts = {}
        spec = {  # name: (size px, semibold, family)
            "body": (14, False, body), "small": (12, False, body), "strong": (14, True, strong or body),
            "large": (17, False, body), "subtitle": (19, True, display or strong or body),
            "title": (24, True, display or strong or body), "mono": (13, False, body),
        }
        for k, (size, semi, fam) in spec.items():
            # A real "Semibold" family is already bold; otherwise ask for bold.
            weight = "bold" if semi and fam == body else "normal"
            self.fonts[k] = tkfont.Font(root, family=fam, size=-size, weight=weight)
        self.fonts["link"] = tkfont.Font(root, family=body, size=-14)
        self.fonts["link_hover"] = tkfont.Font(root, family=body, size=-14, underline=True)
        self.fonts["entry_big"] = tkfont.Font(root, family=body, size=-17)
        for named in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(named, root).configure(family=body, size=-14)
            except Exception:
                pass

    @property
    def c(self):
        return PALETTE[self.name]

    def apply(self, name):
        self.name = "dark" if name == "dark" else "light"
        if self.sv:
            sv_ttk.set_theme(self.name, self.root)
            # Sun Valley's own fonts: same family as the rest of the app.
            for sv_name, key in (("SunValleyBodyFont", "body"), ("SunValleyCaptionFont", "small"),
                                 ("SunValleyBodyStrongFont", "strong"), ("SunValleyBodyLargeFont", "large"),
                                 ("SunValleySubtitleFont", "subtitle"), ("SunValleyTitleFont", "title")):
                try:
                    tkfont.nametofont(sv_name, self.root).configure(**self.fonts[key].actual())
                except Exception:
                    pass
        else:
            try:
                self.style.theme_use("clam")
            except tk.TclError:
                pass
            self.root.configure(bg=self.c["bg"])
            self.style.configure(".", background=self.c["bg"], foreground=self.c["fg"], font=self.fonts["body"])
        c, f, s = self.c, self.fonts, self.style
        s.configure("TLabelframe.Label", font=f["strong"], foreground=c["fg"])
        s.configure("TLabelframe", padding=(12, 4, 12, 7) if self.compact else (14, 8, 14, 12))
        s.configure("Muted.TLabel", foreground=c["muted"], font=f["small"])
        s.configure("Info.TLabel", foreground=c["accent"], font=f["body"])
        s.configure("Ok.TLabel", foreground=c["ok"], font=f["small"])
        s.configure("Warn.TLabel", foreground=c["warn"], font=f["small"])
        s.configure("Busy.TLabel", foreground=c["accent"], font=f["small"])
        s.configure("Title.TLabel", font=f["title"], foreground=c["fg"])
        s.configure("Subtitle.TLabel", font=f["subtitle"], foreground=c["fg"])
        s.configure("Strong.TLabel", font=f["strong"], foreground=c["fg"])
        s.configure("Body.TLabel", font=f["body"], foreground=c["fg"])
        s.configure("Pill.TLabel", font=f["small"], foreground=c["accent"], padding=(8, 1))
        s.configure("Link.TLabel", foreground=c["accent"], font=f["link"])
        s.configure("Small.TButton", padding=(5, 1, 5, 2))
        s.configure("Big.Accent.TButton", padding=(18, 6, 18, 7), font=f["strong"])
        s.configure("Header.TFrame", background=c["header"])
        for st in ("Header.TLabel", "HeaderMuted.TLabel", "HeaderTitle.TLabel", "HeaderPill.TLabel"):
            s.configure(st, background=c["header"])
        s.configure("HeaderTitle.TLabel", font=f["subtitle"], foreground=c["fg"])
        s.configure("HeaderMuted.TLabel", font=f["small"], foreground=c["muted"])
        s.configure("HeaderPill.TLabel", font=f["small"], foreground=c["accent"])
        s.configure("Status.TFrame", background=c["header"])
        s.configure("Status.TLabel", background=c["header"], foreground=c["muted"], font=f["small"])
        s.configure("Thin.Horizontal.TProgressbar", thickness=4)


class SmokeButton(tk.Canvas):
    """The accent button with a few small smoke wisps curling off its outline.

    Tk cannot draw on top of a ttk widget, so the real ttk.Button sits on a slightly larger
    canvas and the smoke is drawn in the margin around it. The puffs start at the button's
    edge, are covered by the button itself, and fade into the card background as they rise.
    The wisps are hidden until steam() starts a short burst. Keeping the real button means
    its normal theme, keyboard and disabled states still work.
    """

    PAD_X = 17
    PAD_TOP = 32
    PAD_BOTTOM = 2
    STAGES = 12
    TICK_MS = 60
    FADE_S = 0.65
    PER_EMITTER = 7
    # fx, fy (from the button's top-left), drift x, rise, starting phase, sway
    EMITTERS = ((0.16, 1, -6, 21, 0.05, 3.2),
                (0.50, 1, 2, 23, 0.41, 3.6),
                (0.84, 1, 7, 20, 0.73, 3.0),
                (-0.01, 15, -9, 15, 0.58, 2.8),
                (1.01, 15, 9, 15, 0.12, 2.8))

    def __init__(self, parent, theme, text, command, style):
        self.theme = theme
        super().__init__(parent, borderwidth=0, highlightthickness=0, bd=0)
        self.button = ttk.Button(self, text=text, command=command, style=style)
        self._win = self.create_window(self.PAD_X, self.PAD_TOP, window=self.button, anchor="nw")
        self._button_w = None
        self._puffs = []
        self._items = []
        self._stage_images = []
        self._job = None
        self._active = False
        self._steam_start = 0.0
        self._steam_until = 0.0
        self._build_puffs()
        self.set_theme()
        self.button.bind("<Configure>", lambda e: self._size(), add="+")

    def _build_puffs(self):
        for e, (fx, fy, drift, rise, phase, sway) in enumerate(self.EMITTERS):
            for k in range(self.PER_EMITTER):
                self._puffs.append(dict(fx=fx, fy=fy, drift=drift, rise=rise, sway=sway, seed=e + k * 0.07,
                                        base=(phase + k / float(self.PER_EMITTER)) % 1.0, ox=0, oy=0))
        for _p in self._puffs:
            self._items.append(self.create_image(-100, -100, anchor="center", state="hidden"))

    def _frame_bg(self):
        for style in ("TLabelframe", "TFrame", "TLabel"):
            try:
                colour = self.theme.style.lookup(style, "background")
            except tk.TclError:
                colour = None
            if colour:
                return colour
        return self.theme.c["bg"]

    def _size(self):
        try:
            req = max(1, self.button.winfo_reqwidth())
            h = max(1, self.button.winfo_reqheight())
        except tk.TclError:
            return
        if self._button_w is None or req > self._button_w:
            self._button_w = req
        self.configure(width=self._button_w + 2 * self.PAD_X, height=h + self.PAD_TOP + self.PAD_BOTTOM)
        self.coords(self._win, self.PAD_X, self.PAD_TOP)
        self.itemconfigure(self._win, width=self._button_w)
        for p in self._puffs:
            p["ox"] = self.PAD_X + p["fx"] * self._button_w
            p["oy"] = self.PAD_TOP + p["fy"]

    @staticmethod
    def _rgb(colour):
        colour = colour.lstrip("#")
        return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))

    @staticmethod
    def _sprite(colour, diameter, alpha):
        # Draw large and soft, then shrink, so even the little puffs have no hard edge.
        box = max(10, int(diameter * 4))
        im = Image.new("RGBA", (box, box), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = box / 2.0
        rx, ry = box * 0.28, box * 0.33
        d.ellipse((c - rx, c - ry, c + rx, c + ry), fill=colour + (int(alpha * 255),))
        im = im.filter(ImageFilter.GaussianBlur(box * 0.10))
        return im.resize((max(1, int(diameter)), max(1, int(diameter))), Image.Resampling.LANCZOS)

    def _make_images(self):
        dark = self.theme.name == "dark"
        colour = self._rgb("#f2f7fc" if dark else "#4d5762")
        images = []
        for i in range(self.STAGES):
            t = i / (self.STAGES - 1.0)
            alpha = (0.40 if dark else 0.30) * (1.0 - t) ** 0.9
            images.append(ImageTk.PhotoImage(self._sprite(colour, 4.5 + 12.0 * t, alpha)))
        return images

    def set_theme(self):
        """Recolour the canvas and rebuild the smoke after a light/dark switch."""
        self.configure(bg=self._frame_bg())
        self._stage_images = self._make_images()
        for item in self._items:
            self.itemconfigure(item, image=self._stage_images[0])
        if not self._active:
            for item in self._items:
                self.itemconfigure(item, state="hidden")
        self._button_w = None
        self.after_idle(self._size)

    def steam(self, duration_ms=4000):
        """Make the wisps appear for a short burst, then fade away again."""
        now = time.monotonic()
        self._steam_start = now
        self._steam_until = now + max(0.2, duration_ms / 1000.0)
        if not self._active:
            self._active = True
            for item in self._items:
                self.itemconfigure(item, state="normal")
            if self._job is None:
                self._tick()

    def _quiet(self):
        self._active = False
        for item in self._items:
            self.itemconfigure(item, state="hidden")
        self._job = None

    def _tick(self):
        self._job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if not self._active:
            return
        now = time.monotonic()
        if now >= self._steam_until:
            self._quiet()
            return
        delay = self.TICK_MS
        if self.winfo_viewable() and self._stage_images and self._button_w:
            # Thin the smoke out over the last moment instead of snapping it off.
            fade = self._steam_until - now
            if fade < self.FADE_S:
                keep = fade / self.FADE_S
                n = max(1, len(self._items) - 1)
                for i, item in enumerate(self._items):
                    rank = ((i * 17) % len(self._items)) / n
                    self.itemconfigure(item, state="normal" if rank <= keep else "hidden")
            elapsed = now - self._steam_start
            for p, item in zip(self._puffs, self._items):
                a = (elapsed * 0.34 + p["base"]) % 1.0
                wave = math.sin(a * math.tau * 1.2 + p["seed"] * 9) * p["sway"] * a
                x = p["ox"] + p["drift"] * a + wave + math.sin(a * math.tau * 2.7 + p["seed"] * 4) * 0.7 * a
                y = p["oy"] - p["rise"] * a - wave * 0.18
                stage = min(self.STAGES - 1, int(a * self.STAGES))
                self.coords(item, x, y)
                self.itemconfigure(item, image=self._stage_images[stage])
        else:
            delay = 250                      # hidden or not laid out yet: do not spin the event loop
        self._job = self.after(delay, self._tick)

    def destroy(self):
        if self._job:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        super().destroy()


class ScrollArea(ttk.Frame):
    """A column that scrolls when the window is too short for it. The scrollbar only shows when
    it is needed. The mouse wheel is handled by App._on_wheel."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, width=10, height=10,
                                yscrollincrement=24)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.vsb.grid_remove()
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)
        # These fire a lot: on every step of a window resize, and the inner frame on every scroll
        # (it moves). Each handler only touches widgets when a size really changed, otherwise a
        # resize drag turns into a stream of relayouts and the window tears.
        self._req = None            # inner frame's requested size last applied to the canvas
        self._item_w = None         # width last given to the inner frame's canvas item
        self._bar_after = None
        self._wheel = 0             # wheel steps waiting to be applied
        self._wheel_after = None
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)

    def _on_inner(self, e=None):
        req = (self.inner.winfo_reqwidth(), self.inner.winfo_reqheight())
        if req == self._req:
            return                  # it only moved (scrolling) or was stretched to the canvas width
        self._req = req
        w, h = req
        # Ask for the whole column: on a big screen the window opens tall enough and never scrolls.
        self.canvas.configure(width=w, height=h, scrollregion=(0, 0, w, h))
        self._apply_width()
        self._schedule_bar()

    def _on_canvas(self, e=None):
        self._apply_width()
        self._schedule_bar()

    def _apply_width(self):
        w = max(self.canvas.winfo_width(), self.inner.winfo_reqwidth())
        if w != self._item_w:
            self._item_w = w
            self.canvas.itemconfigure(self._win, width=w)

    def refresh(self):
        """Apply a change of the column's content now (used after the layout mode changes)."""
        self._on_inner()
        self._update_bar()

    def needed(self):
        return self.inner.winfo_reqheight() > self.canvas.winfo_height() + 1

    def _schedule_bar(self):
        # Showing or hiding the scrollbar changes the column width and so relayouts the whole
        # window: wait until a resize drag settles.
        if self._bar_after:
            self.after_cancel(self._bar_after)
        self._bar_after = self.after(150, self._update_bar)

    def _update_bar(self):
        self._bar_after = None
        if self.canvas.winfo_height() <= 1:
            return
        over = self.inner.winfo_reqheight() - self.canvas.winfo_height()
        shown = bool(self.vsb.winfo_manager())
        if not shown and over > 1:
            self.vsb.grid()
        elif shown and over <= -4:              # a little slack so it does not flicker at the edge
            self.vsb.grid_remove()
            self.canvas.yview_moveto(0)

    def contains(self, w):
        p = str(self) + "."
        return w is not None and (str(w) + ".").startswith(p)

    def scroll(self, units):
        # Wheels can send many events per frame (touchpads, fast spins): add them up and scroll once.
        if not units:
            return
        self._wheel += units
        if self._wheel_after is None:
            self._wheel_after = self.after_idle(self._do_scroll)

    def _do_scroll(self):
        n, self._wheel, self._wheel_after = self._wheel, 0, None
        if n and self.needed():
            self.canvas.yview_scroll(n, "units")

    def set_bg(self, colour):
        self.canvas.configure(bg=colour)


class FontList(tk.Canvas):
    """Fonts drawn in their own typeface, one row each.

    A Listbox draws every row in one font, so the rows are drawn on a canvas instead: the
    name and a short sample, both in the font itself. Only the rows on screen are drawn,
    which keeps a machine with hundreds of fonts responsive.

    on_pick(name) fires when a row is chosen, on_accept(name) on a double-click.
    """

    ROW_H = 42
    SAMPLE_W = 128

    def __init__(self, parent, theme, rows=6, on_pick=None, on_accept=None, sample="Aa Bb 123"):
        super().__init__(parent, highlightthickness=1, borderwidth=0,
                         height=rows * self.ROW_H, width=240)
        self.theme = theme
        self.rows = rows
        self.sample = sample
        self.on_pick = on_pick
        self.on_accept = on_accept
        self.fonts = []
        self.current = None
        self.hover = None
        self._faces = {}
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.bind("<Button-1>", self._on_click)
        self.bind("<Double-Button-1>", self._on_double)
        self.bind("<MouseWheel>", lambda e: self.scroll(-1 if e.delta > 0 else 1))
        self.bind("<Button-4>", lambda e: self.scroll(-2))
        self.bind("<Button-5>", lambda e: self.scroll(2))
        self.set_theme()

    # ---------------------------------------------------------------- appearance
    def set_theme(self):
        c = self.theme.c
        self.configure(bg=c["bg"], highlightbackground=c["border"], highlightcolor=c["accent"])
        self._faces = {}                  # families can render differently after a theme switch
        self.redraw()

    def set_rows(self, rows):
        self.rows = rows
        self.configure(height=rows * self.ROW_H)
        self.redraw()

    def _on_accent(self):
        return "#ffffff" if self.theme.name == "light" else "#0d1420"

    def _face(self, f, px):
        key = ((f.get("family") or f.get("name") or ""), px)
        face = self._faces.get(key)
        if face is None:
            try:
                face = tkfont.Font(self, family=key[0], size=-px)
            except tk.TclError:
                face = self.theme.fonts["body"]
            self._faces[key] = face
        return face

    @staticmethod
    def _fit(face, text, max_px):
        """Trim to the width, with an ellipsis, so a long name cannot collide with the sample."""
        try:
            if face.measure(text) <= max_px:
                return text
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if face.measure(text[:mid] + "…") <= max_px:
                    lo = mid
                else:
                    hi = mid - 1
            return text[:lo] + "…"
        except tk.TclError:
            return text

    # ---------------------------------------------------------------- data
    def set_fonts(self, fonts, current=None):
        self.fonts = list(fonts)
        if current is not None:
            self.current = current
        self.redraw()
        self.after_idle(self.see_current)

    def set_current(self, name):
        self.current = name
        self.redraw()

    def see_current(self):
        """Scroll so the chosen font is visible (does nothing before the first layout)."""
        if not self.current or not self.fonts:
            return
        names = [f["name"] for f in self.fonts]
        if self.current not in names:
            return
        i = names.index(self.current)
        top, view = self.canvasy(0), self.winfo_height()
        y = i * self.ROW_H
        if y < top or y + self.ROW_H > top + view:
            total = max(1, len(self.fonts) * self.ROW_H)
            self.yview_moveto(max(0.0, (y - view / 2.0) / total))

    # ---------------------------------------------------------------- drawing
    def redraw(self):
        self.delete("row")
        w = max(self.winfo_width(), 40)
        total = max(1, len(self.fonts) * self.ROW_H)
        self.configure(scrollregion=(0, 0, w, total))
        if not self.fonts:
            self.create_text(w / 2, 30, text="No fonts found", fill=self.theme.c["muted"],
                             font=self.theme.fonts["body"], tags="row")
            return
        top, view = self.canvasy(0), self.winfo_height()
        first = max(0, int(top // self.ROW_H))
        last = min(len(self.fonts), int((top + view) // self.ROW_H) + 2)
        for i in range(first, last):
            self._row(i, w)

    def _row(self, i, w):
        f = self.fonts[i]
        name = f["name"]
        y = i * self.ROW_H
        chosen = name == self.current
        if chosen or name == self.hover:
            fill = self.theme.c["accent"] if chosen else self.theme.c["preview"]
            self.create_rectangle(2, y + 1, w - 2, y + self.ROW_H - 2,
                                  fill=fill, outline="", tags="row")
        fg = self._on_accent() if chosen else self.theme.c["fg"]
        face = self._face(f, 15)
        self.create_text(12, y + self.ROW_H / 2, anchor="w", tags="row", fill=fg, font=face,
                         text=self._fit(face, name, w - self.SAMPLE_W - 34))
        sface = self._face(f, 13)
        self.create_text(w - 12, y + self.ROW_H / 2, anchor="e", tags="row",
                         fill=fg if chosen else self.theme.c["muted"], font=sface,
                         text=self._fit(sface, self.sample, self.SAMPLE_W))

    # ---------------------------------------------------------------- interaction
    def _index_at(self, event):
        i = int(self.canvasy(event.y) // self.ROW_H)
        return i if 0 <= i < len(self.fonts) else None

    def _set_hover(self, name):
        if name != self.hover:
            self.hover = name
            self.redraw()

    def _on_motion(self, event):
        i = self._index_at(event)
        self._set_hover(self.fonts[i]["name"] if i is not None else None)

    def _on_click(self, event):
        i = self._index_at(event)
        if i is None:
            return
        self.set_current(self.fonts[i]["name"])
        if self.on_pick:
            self.on_pick(self.current)

    def _on_double(self, event):
        i = self._index_at(event)
        if i is None:
            return
        self.set_current(self.fonts[i]["name"])
        if self.on_accept:
            self.on_accept(self.current)

    def scroll(self, units):
        """Wheel scrolling: keep it to whole rows so the list never lands mid-row."""
        if not self.fonts:
            return
        top = self.canvasy(0)
        total = max(1, len(self.fonts) * self.ROW_H)
        self.yview_moveto(max(0.0, min(1.0, (top + units * self.ROW_H) / total)))


class FontChooser(tk.Toplevel):
    """A big font picker: every font listed in its own typeface, with a live preview.

    Picking a row previews it; double-click or "Use this font" applies it.
    """

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.theme = app.theme
        self.withdraw()
        self.title("Choose a font")
        self.transient(parent)
        self.configure(bg=self.theme.c["bg"])
        self.minsize(760, 520)

        head = ttk.Frame(self, padding=(16, 14, 16, 6))
        head.pack(fill="x")
        ttk.Label(head, text="Choose a font", font=self.theme.fonts["large"]).pack(side="left")
        ttk.Label(head, text="Every name is drawn in its own typeface",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))

        row = ttk.Frame(self, padding=(16, 0, 16, 8))
        row.pack(fill="x")
        ttk.Label(row, text="Search", style="Muted.TLabel").pack(side="left", padx=(0, 8))
        self.v_search = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.v_search)
        entry.pack(side="left", fill="x", expand=True)
        self.v_search.trace_add("write", lambda *a: self._filter())

        body = ttk.Frame(self, padding=(16, 0, 16, 0))
        body.pack(fill="both", expand=True)
        # The preview keeps a fixed width so the font list gets every spare pixel.
        right = ttk.Frame(body, width=300)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 16))

        self.list = FontList(left, self.theme, rows=9, on_pick=self._preview,
                             on_accept=self._use_name)
        sb = ttk.Scrollbar(left, command=self.list.yview)
        self.list.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(4, 0))
        self.list.pack(side="left", fill="both", expand=True)

        self.preview = tk.Canvas(right, bg=self.theme.c["preview"], highlightthickness=1,
                                 highlightbackground=self.theme.c["border"], height=200)
        self.preview.pack(fill="x")
        self.preview.bind("<Configure>", lambda e: self._draw_preview())
        self.l_name = ttk.Label(right, style="Info.TLabel", wraplength=280)
        self.l_name.pack(anchor="w", pady=(10, 0))
        self.l_hint = ttk.Label(right, style="Muted.TLabel", wraplength=280,
                                text="This is how your wording will look. Double-click a name to apply it.")
        self.l_hint.pack(anchor="w", pady=(6, 0))

        foot = ttk.Frame(self, padding=(16, 12, 16, 16))
        foot.pack(side="bottom", fill="x")
        style = "Big.Accent.TButton" if self.theme.sv else "TButton"
        ttk.Button(foot, text="Use this font", style=style, command=self._use).pack(side="right")
        ttk.Button(foot, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 8))

        self._filter()
        self.update_idletasks()
        w = min(980, max(760, parent.winfo_width() - 80))
        h = min(720, max(520, parent.winfo_height() - 80))
        self.geometry("%dx%d+%d+%d" % (w, h,
                                       parent.winfo_rootx() + (parent.winfo_width() - w) // 2,
                                       parent.winfo_rooty() + (parent.winfo_height() - h) // 2))
        self.deiconify()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._use())
        self.bind("<Down>", lambda e: self._step(1))
        self.bind("<Up>", lambda e: self._step(-1))
        entry.focus_set()

    def _step(self, delta):
        """Arrow keys walk the filtered list, so the search box keeps the keyboard."""
        fonts = self.list.fonts
        if not fonts:
            return "break"
        names = [f["name"] for f in fonts]
        i = names.index(self.list.current) if self.list.current in names else -1
        i = max(0, min(len(names) - 1, i + delta))
        self.list.set_current(names[i])
        self.list.see_current()
        self._draw_preview()
        return "break"

    def _filter(self):
        q = self.v_search.get().strip().lower()
        fonts = [f for f in self.app.fonts if q in f["name"].lower()]
        names = [f["name"] for f in fonts]
        current = self.list.current or self.app.s.get("font")
        if current not in names:
            current = names[0] if names else None
        self.list.set_fonts(fonts, current)
        self._draw_preview()

    def _preview(self, name):
        self.list.set_current(name)
        self._draw_preview()

    def _draw_preview(self):
        cv = self.preview
        cv.delete("all")
        w, h = max(cv.winfo_width(), 60), max(cv.winfo_height(), 60)
        name = self.list.current
        f = self.app.font_by_name.get(name) if name else None
        if not f:
            self.l_name.configure(text="")
            return
        family = f.get("family") or f["name"]
        wording = (self.app.v_text.get() or "").strip() or "Workshop"
        px = 44
        face = tkfont.Font(self, family=family, size=-px)
        while px > 12:
            face = tkfont.Font(self, family=family, size=-px)
            try:
                fits = (face.measure(wording) <= w - 24
                        and face.metrics("linespace") <= h - 20)
            except tk.TclError:
                fits = True
            if fits:
                break
            px -= 2
        cv.create_text(w / 2, h / 2, text=wording, font=face, fill=self.theme.c["fg"])
        self.l_name.configure(text="%s   ·   %s" % (f["name"], f.get("style") or "Regular"))

    def _use(self):
        self._use_name(self.list.current)

    def _use_name(self, name):
        if name:
            self.app.set_font(name)
        self.destroy()


class Link(ttk.Label):
    """A label that opens a web page, underlined on hover."""

    def __init__(self, master, text, url, theme, **kw):
        super().__init__(master, text=text, style="Link.TLabel", cursor="hand2", **kw)
        self.url, self.theme = url, theme
        self.bind("<Button-1>", lambda e: open_url(self.url))
        self.bind("<Enter>", lambda e: self.configure(font=theme.fonts["link_hover"]))
        self.bind("<Leave>", lambda e: self.configure(font=theme.fonts["link"]))


# ---------------------------------------------------------------- About
class AboutDialog(tk.Toplevel):
    """Help > About: centred, modal, Sun Valley styled."""

    def __init__(self, parent, theme, modal=True):
        super().__init__(parent)
        self.withdraw()
        self.theme = theme
        c = theme.c
        self.title("About Sign Maker")
        self.resizable(False, False)
        self.configure(bg=c["bg"])
        self.transient(parent)
        wrap = 470
        outer = ttk.Frame(self, padding=(34, 26, 34, 22)); outer.pack(fill="both", expand=True)

        self._icon = icon_image(96)
        if self._icon is not None:
            ttk.Label(outer, image=self._icon).pack(pady=(0, 10))
        ttk.Label(outer, text=APP_NAME, style="Subtitle.TLabel").pack()
        ttk.Label(outer, text="Version " + __version__, style="Pill.TLabel").pack(pady=(2, 10))
        ttk.Label(outer, text="Type your wording, pick a font and colours, and Sign Maker builds a two-colour "
                              "sign ready for your slicer: a plate with raised or inlaid lettering, saved as one "
                              "3MF with a dimension picture.",
                  style="Body.TLabel", wraplength=wrap, justify="center").pack()

        ttk.Label(outer, text="Created by " + AUTHOR, style="Strong.TLabel").pack(pady=(16, 2))
        row = ttk.Frame(outer); row.pack()
        Link(row, "github.com/postmanpat-303", AUTHOR_URL, theme).pack(side="left")
        ttk.Label(row, text="  ·  ", style="Muted.TLabel").pack(side="left")
        Link(row, "Source code", REPO_URL, theme).pack(side="left")
        ttk.Label(row, text="  ·  ", style="Muted.TLabel").pack(side="left")
        Link(row, "Releases", RELEASES_URL, theme).pack(side="left")

        ttk.Label(outer, text="If you find Sign Maker useful, you can buy me a coffee ☕",
                  style="Body.TLabel", wraplength=wrap, justify="center").pack(pady=(18, 8))
        ttk.Button(outer, text="☕  Buy me a coffee", style="Big.Accent.TButton",
                   command=lambda: open_url(DONATE_URL)).pack()
        row = ttk.Frame(outer); row.pack(pady=(6, 0))
        ttk.Label(row, text="or PayPal:", style="Muted.TLabel").pack(side="left", padx=(0, 4))
        Link(row, "paypal.me/derekh100", PAYPAL_URL, theme).pack(side="left")

        ttk.Separator(outer).pack(fill="x", pady=16)
        ttk.Label(outer, text="Built with SolidCraft  ♥", style="Strong.TLabel").pack()
        ttk.Label(outer, text="Every 3D model Sign Maker makes is built by SolidCraft, the open-source parametric "
                              "3D CAD from Tangency Labs. Sign Maker wouldn't exist without it. A big, warm thank "
                              "you to the SolidCraft team for such a great tool.",
                  style="Body.TLabel", wraplength=wrap, justify="center").pack(pady=(4, 4))
        Link(outer, "github.com/tangency-labs/solidcraft", SOLIDCRAFT_URL, theme).pack()

        ttk.Separator(outer).pack(fill="x", pady=16)
        ttk.Label(outer, text="Sign Maker is an unofficial community add-on. It is not affiliated with or endorsed "
                              "by Tangency Labs or the SolidCraft project. SolidCraft is installed separately.",
                  style="Muted.TLabel", wraplength=wrap, justify="center").pack()
        row = ttk.Frame(outer); row.pack(pady=(8, 0))
        Link(row, "MIT licence", LICENSE_URL, theme).pack(side="left")
        ttk.Label(row, text="  ·  © 2026 " + AUTHOR, style="Muted.TLabel").pack(side="left")
        ttk.Label(outer, text="Thanks. :)", style="Muted.TLabel").pack(pady=(6, 0))
        close = ttk.Button(outer, text="Close", command=self.close, width=12)
        close.pack(pady=(16, 0))

        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Return>", lambda e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        clear_labels(self)
        centre_window(self, parent)
        self.deiconify()
        if modal:
            try:
                self.wait_visibility()
                self.grab_set()
            except tk.TclError:
                pass
        close.focus_set()

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


# ---------------------------------------------------------------- main window
class App:
    def __init__(self, root, selftest=False):
        self.root = root
        apply_window_icon(root)
        self.s = sc.load_settings()
        self.fonts, self.font_by_name = [], {}
        self._shown = []
        self.q = queue.Queue()
        self.busy = False            # Make 3MF running
        self._sparkle_gen = 0        # bumps to stop a twinkle on the Make button
        self.last_folder = None
        self._after = None
        self._cli = None
        # 3D preview state
        self._gen = 0                # bumps on every 3D request; older results are ignored
        self._job = None             # the 3D preview build that is running
        self._after3d = None
        self._cur = None             # (params, font, key) of the latest valid design
        self._shown_key = None       # design shown in the 3D view
        self._im3d = None            # PIL image shown in the 3D view
        self._mask3d = None          # where its backdrop is, so dark theme can recolour it
        self._w2d = 0                # width the 2D preview was last drawn at
        self._fit_after = None
        self._compact = None         # compact layout for short screens (None until first decided)
        self._tight = False          # very short screen: smaller 2D preview still
        self._max2d_h = 360          # tallest the 2D preview may be drawn
        self._layout_after = None
        self._last_work = None
        self._2d_after = None
        self._2d_limit = 1100        # widest the 2D preview may be for the current plate
        self._fit_key = None         # (image, theme, size) the 3D view was last fitted for
        self._dark3d = None          # (image, recoloured copy) for the dark theme
        self.theme = Theme(root)
        self.theme.apply(self.s.get("theme", "light"))
        root.title(APP_NAME)
        self._build_menu()
        self._build_ui()
        self._apply_widget_colours()
        self._update_layout()
        # A binding on the root also runs for every child widget's <Configure> (the toplevel is
        # in their bind tags), dozens per resize step. Use a tag only the root window has.
        root.bindtags(("SignMakerTop",) + root.bindtags())
        root.bind_class("SignMakerTop", "<Configure>", self._on_root_configure)
        self._last_geom = None
        self._refresh_cli_field()
        self._set_3d_state("idle")
        if selftest:
            self._load_fonts_sync()
        else:
            threading.Thread(target=self._load_fonts_thread, daemon=True).start()
            root.after(100, self._poll)
            root.after(400, self._maybe_prompt_cli)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- menu
    def _build_menu(self):
        r = self.root
        mod = "Command" if sys.platform == "darwin" else "Ctrl"
        mb = tk.Menu(r)
        fm = tk.Menu(mb, tearoff=False)
        fm.add_command(label="Make 3MF", accelerator=mod + "+M", command=self.make)
        fm.add_command(label="Open signs folder", command=self.open_signs_root)
        fm.add_separator()
        fm.add_command(label="Save folder…", command=self.browse_output)
        fm.add_command(label="SolidCraft path…", command=self.browse_cli)
        fm.add_separator()
        fm.add_command(label="Exit", accelerator=mod + "+Q", command=self.on_close)
        mb.add_cascade(label="File", menu=fm)

        self.v_auto3d = tk.BooleanVar(value=bool(self.s.get("auto_preview", True)))
        self.v_theme = tk.StringVar(value=self.theme.name)
        vm = tk.Menu(mb, tearoff=False)
        vm.add_checkbutton(label="Auto 3D preview", variable=self.v_auto3d, command=self._on_auto3d)
        vm.add_command(label="Refresh 3D preview", accelerator="F5", command=lambda: self.refresh_3d(manual=True))
        vm.add_separator()
        vm.add_radiobutton(label="Light theme", value="light", variable=self.v_theme, command=self._on_theme)
        vm.add_radiobutton(label="Dark theme", value="dark", variable=self.v_theme, command=self._on_theme)
        mb.add_cascade(label="View", menu=vm)

        hm = tk.Menu(mb, tearoff=False)
        hm.add_command(label="About Sign Maker", command=self.show_about)
        hm.add_separator()
        hm.add_command(label="Sign Maker on GitHub", command=lambda: open_url(REPO_URL))
        hm.add_command(label="Check for new releases", command=self.check_updates)
        hm.add_command(label="Get SolidCraft", command=lambda: open_url(SOLIDCRAFT_RELEASES))
        mb.add_cascade(label="Help", menu=hm)
        r.config(menu=mb)
        self.menus = [mb, fm, vm, hm]

        key = "Command" if sys.platform == "darwin" else "Control"
        r.bind_all("<F5>", lambda e: self.refresh_3d(manual=True))
        r.bind_all("<%s-m>" % key, lambda e: self.make())
        r.bind_all("<%s-q>" % key, lambda e: self.on_close())

    # ---------------- UI
    def _card(self, parent, title):
        return ttk.LabelFrame(parent, text=title)

    def _build_ui(self):
        r = self.root
        r.columnconfigure(0, weight=1); r.rowconfigure(1, weight=1)

        # header
        hd = ttk.Frame(r, style="Header.TFrame", padding=(18, 10, 18, 10)); hd.grid(row=0, column=0, sticky="we")
        self._hd = hd
        self._hicon = icon_image(40)
        if self._hicon is not None:
            ttk.Label(hd, image=self._hicon, style="Header.TLabel").pack(side="left", padx=(0, 12))
        tbox = ttk.Frame(hd, style="Header.TFrame"); tbox.pack(side="left")
        ttk.Label(tbox, text="Sign Maker", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(tbox, text="Two-colour 3D-print signs, built with SolidCraft",
                  style="HeaderMuted.TLabel").pack(anchor="w")
        ttk.Label(hd, text="v" + __version__, style="HeaderPill.TLabel").pack(side="right")
        self.v_dark = tk.BooleanVar(value=self.theme.name == "dark")
        ttk.Checkbutton(hd, text="Dark", style="Switch.TCheckbutton" if self.theme.sv else "TCheckbutton",
                        variable=self.v_dark, command=self._on_dark_switch).pack(side="right", padx=(0, 18))

        body = ttk.Frame(r, padding=(14, 10, 14, 4)); body.grid(row=1, column=0, sticky="nsew")
        self._body = body
        body.columnconfigure(1, weight=1); body.rowconfigure(0, weight=1)
        # The left column scrolls when the screen is too short for it (small laptops, display scaling).
        self.scroll = ScrollArea(body); self.scroll.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        left = self.scroll.inner
        right = ttk.Frame(body); right.grid(row=0, column=1, sticky="nsew")
        left.columnconfigure(0, weight=1)

        # --- wording + favourites
        wc = self._card(left, "Wording"); wc.grid(row=0, column=0, sticky="we", pady=(0, 8))
        self._gap_cards = [wc]
        self.v_text = tk.StringVar(value=self.s["text"])
        self.e_text = ttk.Entry(wc, textvariable=self.v_text, font=self.theme.fonts["entry_big"])
        self.e_text.grid(row=0, column=0, columnspan=4, sticky="we")
        acc = ttk.Frame(wc); acc.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 6))
        for ch in "áéíóúÁÉÍÓÚ⁊":
            ttk.Button(acc, text=ch, width=2, style="Small.TButton",
                       command=lambda c=ch: self._insert(c)).pack(side="left", padx=(0, 3))
        ttk.Label(wc, text="Favourites", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 6))
        self.cb_fav = ttk.Combobox(wc, width=22, state="readonly"); self.cb_fav.grid(row=2, column=1, sticky="we")
        fb = ttk.Frame(wc); fb.grid(row=2, column=2, columnspan=2, sticky="e", padx=(6, 0))
        ttk.Button(fb, text="Use", command=self.use_fav, style="Small.TButton").pack(side="left", padx=(0, 3))
        ttk.Button(fb, text="Add", command=self.add_fav, style="Small.TButton").pack(side="left", padx=(0, 3))
        ttk.Button(fb, text="Remove", command=self.del_fav, style="Small.TButton").pack(side="left")
        wc.columnconfigure(1, weight=1)
        self._refresh_favs()

        # --- font
        fc = self._card(left, "Font"); fc.grid(row=1, column=0, sticky="we", pady=(0, 8))
        self._gap_cards.append(fc)
        self.v_search = tk.StringVar()
        se = ttk.Frame(fc); se.grid(row=0, column=0, sticky="we")
        ttk.Label(se, text="Search", style="Muted.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(se, textvariable=self.v_search).pack(side="left", fill="x", expand=True)
        fl = ttk.Frame(fc); fl.grid(row=1, column=0, sticky="we", pady=(6, 4))
        self._lbframe = fl
        self.fontlist = FontList(fl, self.theme, rows=6, on_pick=self._on_font_pick,
                                 on_accept=self.open_font_chooser)
        sb = ttk.Scrollbar(fl, command=self.fontlist.yview)
        self.fontlist.configure(yscrollcommand=sb.set)
        self.fontlist.pack(side="left", fill="both", expand=True); sb.pack(side="left", fill="y", padx=(4, 0))
        fr = ttk.Frame(fc); fr.grid(row=2, column=0, sticky="we", pady=(4, 0))
        self.v_fontname = tk.StringVar(value=self.s["font"])
        ttk.Label(fr, textvariable=self.v_fontname, style="Info.TLabel").pack(side="left")
        ttk.Button(fr, text="Choose font…", command=self.open_font_chooser).pack(side="right")
        ttk.Button(fr, text="Browse…", command=self.browse_font, style="Small.TButton").pack(
            side="right", padx=(0, 6))
        self.v_bold = tk.BooleanVar(value=self.s.get("bold", False))
        ttk.Checkbutton(fc, text="Bold (uses the family's bold face)", variable=self.v_bold).grid(
            row=3, column=0, sticky="w", pady=(4, 0))
        fc.columnconfigure(0, weight=1)

        # --- sizes + style
        nf = self._card(left, "Size and style"); nf.grid(row=2, column=0, sticky="we", pady=(0, 8))
        self._gap_cards.append(nf)
        self.v_num = {}
        for i, (k, lab) in enumerate(NUM_FIELDS):
            ttk.Label(nf, text=lab).grid(row=i // 2, column=(i % 2) * 2, sticky="e", padx=(6, 6), pady=2)
            v = tk.StringVar(value=str(self.s[k])); self.v_num[k] = v
            ttk.Entry(nf, textvariable=v, width=7).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", pady=2)
        row = (len(NUM_FIELDS) + 1) // 2
        self.v_auto = tk.BooleanVar(value=self.s.get("auto_size", True))
        ttk.Checkbutton(nf, text="Auto-fit text size", variable=self.v_auto).grid(row=row, column=0, columnspan=2,
                                                                                  sticky="w", pady=2)
        ttk.Label(nf, text="Cap height (mm)").grid(row=row, column=2, sticky="e", padx=(6, 6))
        self.v_size = tk.StringVar(value=str(self.s.get("text_size", 8)))
        self.e_size = ttk.Entry(nf, textvariable=self.v_size, width=7); self.e_size.grid(row=row, column=3, sticky="w")
        self.v_style = tk.StringVar(value=self.s.get("style", "raised"))
        st = ttk.Frame(nf); st.grid(row=row + 1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(st, text="Text style").pack(side="left", padx=(6, 10))
        ttk.Radiobutton(st, text="Raised", value="raised", variable=self.v_style).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(st, text="Engraved (inlaid, flush)", value="engraved", variable=self.v_style).pack(side="left")

        # --- colours
        cf = self._card(left, "Colours"); cf.grid(row=3, column=0, sticky="we")
        self.v_pc = tk.StringVar(value=self.s["plate_color"]); self.v_tc = tk.StringVar(value=self.s["text_color"])
        self.sw = {}
        for i, (lab, var) in enumerate((("Plate", self.v_pc), ("Text", self.v_tc))):
            ttk.Label(cf, text=lab).grid(row=i, column=0, sticky="e", padx=(6, 8), pady=3)
            b = tk.Button(cf, width=3, bg=var.get(), activebackground=var.get(), relief="flat", borderwidth=0,
                          highlightthickness=1, cursor="hand2", command=lambda v=var: self.pick_colour(v))
            b.grid(row=i, column=1, padx=(0, 8), ipady=3)
            self.sw[str(var)] = b
            ttk.Entry(cf, textvariable=var, width=9).grid(row=i, column=2, pady=3)
            cb = ttk.Combobox(cf, values=[n for n, _ in sc.COLOUR_PRESETS], width=15, state="readonly")
            cb.grid(row=i, column=3, padx=8, pady=3)
            cb.set("Preset…")
            cb.bind("<<ComboboxSelected>>", lambda e, v=var, c=cb: v.set(dict(sc.COLOUR_PRESETS)[c.get()]))
        ttk.Button(cf, text="⇅ Swap", command=self.swap_colours).grid(row=0, column=4, rowspan=2)

        # --- right: 2D preview
        right.columnconfigure(0, weight=1); right.rowconfigure(1, weight=1)
        p2 = self._card(right, "2D preview  ·  true proportions, real font"); p2.grid(row=0, column=0, sticky="we")
        # width=1: the label asks for no width of its own, so the column decides and the
        # picture is drawn to fit it (see _on_2d_resize), never wider than the window.
        self.c2d = tk.Label(p2, borderwidth=0, highlightthickness=0, width=1); self.c2d.pack(fill="x")
        self.c2d.bind("<Configure>", self._on_2d_resize)
        self.v_info = tk.StringVar(value="Loading fonts…")
        self.l_info = ttk.Label(p2, textvariable=self.v_info, style="Info.TLabel")
        self.l_info.pack(anchor="w", pady=(6, 0))

        # --- right: 3D preview
        p3 = self._card(right, "3D preview  ·  rendered by SolidCraft, what will print")
        p3.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        self._p3 = p3
        bar = ttk.Frame(p3); bar.pack(fill="x", pady=(0, 6))
        ttk.Checkbutton(bar, text="Auto 3D preview", variable=self.v_auto3d, command=self._on_auto3d,
                        style="Switch.TCheckbutton" if self.theme.sv else "TCheckbutton").pack(side="left")
        self.b3d = ttk.Button(bar, text="Refresh 3D preview", command=lambda: self.refresh_3d(manual=True))
        self.b3d.pack(side="left", padx=(12, 0))
        self.v_3dstate = tk.StringVar()
        self.l_3dstate = ttk.Label(bar, textvariable=self.v_3dstate, style="Muted.TLabel")
        self.l_3dstate.pack(side="right")
        self.pb3d = ttk.Progressbar(bar, mode="indeterminate", length=90)
        # A fixed-size holder: the picture follows the window, never the other way round.
        self.f3d = tk.Frame(p3, height=320, borderwidth=0, highlightthickness=0)
        self.f3d.pack(fill="both", expand=True); self.f3d.pack_propagate(False)
        self.c3d = tk.Label(self.f3d, borderwidth=0, highlightthickness=0, text="")
        self.c3d.pack(fill="both", expand=True)
        self.f3d.bind("<Configure>", self._on_3d_resize)

        # --- right: make + paths
        oc = self._card(right, "Make the sign"); oc.grid(row=2, column=0, sticky="we")
        bt = ttk.Frame(oc); bt.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 8))
        self.bmk_box = SmokeButton(bt, self.theme, "Make 3MF", self.make,
                                   "Big.Accent.TButton" if self.theme.sv else "TButton")
        self.bmk_box.pack(side="left")
        self.bmk = self.bmk_box.button
        self.bop = ttk.Button(bt, text="Open folder", command=self.open_folder, state="disabled")
        self.bop.pack(side="left", padx=(10, 0), anchor="s", pady=(0, SmokeButton.PAD_BOTTOM))
        self.v_stl = tk.BooleanVar(value=self.s.get("stl", False))
        ttk.Checkbutton(bt, text="Also save separate STLs", variable=self.v_stl).pack(
            side="left", padx=(16, 0), anchor="s", pady=(0, SmokeButton.PAD_BOTTOM))
        ttk.Label(oc, text="Save folder", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.v_out = tk.StringVar(value=sc.output_root(self.s))
        ttk.Entry(oc, textvariable=self.v_out).grid(row=1, column=1, sticky="we", pady=2)
        ttk.Button(oc, text="Browse…", command=self.browse_output, style="Small.TButton").grid(row=1, column=2, padx=(8, 0))
        ttk.Label(oc, text="solidcraft-cli", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10))
        self.v_cli = tk.StringVar(value=(self.s.get("cli_path") or ""))
        ttk.Entry(oc, textvariable=self.v_cli).grid(row=2, column=1, sticky="we", pady=2)
        ttk.Button(oc, text="Browse…", command=self.browse_cli, style="Small.TButton").grid(row=2, column=2, padx=(8, 0))
        self.v_savehint = tk.StringVar()
        self._l_savehint = ttk.Label(oc, textvariable=self.v_savehint, style="Muted.TLabel")
        self._l_savehint.grid(row=3, column=0, columnspan=3,
                                                                           sticky="w", pady=(4, 0))
        oc.columnconfigure(1, weight=1)
        self.v_out.trace_add("write", lambda *a: self._update_save_hint())
        self._update_save_hint()

        # Wheel over the left column scrolls it, except over the font list (which scrolls itself).
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            r.bind_all(seq, self._on_wheel, add="+")
        # A read-only combobox would change its value under the wheel: scroll the column instead.
        stack = [left]
        while stack:
            w = stack.pop(); stack.extend(w.winfo_children())
            if isinstance(w, ttk.Combobox):
                for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    w.bind(seq, self._on_wheel_break)

        # status bar
        sbar = ttk.Frame(r, style="Status.TFrame", padding=(18, 4)); sbar.grid(row=2, column=0, sticky="we")
        self.v_status = tk.StringVar(value="")
        ttk.Label(sbar, textvariable=self.v_status, style="Status.TLabel").pack(side="left")
        ttk.Label(sbar, text="Made by " + AUTHOR + "  ·  Powered by SolidCraft",
                  style="Status.TLabel").pack(side="right")

        for v in [self.v_text, self.v_bold, self.v_auto, self.v_size, self.v_style, self.v_pc, self.v_tc] + list(self.v_num.values()):
            v.trace_add("write", lambda *a: self.schedule())
        self.v_search.trace_add("write", lambda *a: self._fill_list())

    def _apply_widget_colours(self):
        """Plain tk widgets (list, previews, swatches) follow the theme by hand."""
        # Sun Valley calls tk_setPalette, which also stamps a fixed -background on every ttk label
        # (and on new ones, through the option database). Clear it so labels use their style again.
        try:
            self.root.update()
        except tk.TclError:
            pass
        clear_labels(self.root)
        c = self.theme.c
        self.fontlist.set_theme()
        self.c2d.configure(bg=c["preview"])
        try:
            frame_bg = self.theme.style.lookup("TFrame", "background") or c["bg"]
        except tk.TclError:
            frame_bg = c["bg"]
        self.scroll.set_bg(frame_bg)
        self.bmk_box.set_theme()
        self.f3d.configure(bg=c["preview3d"])
        self.c3d.configure(bg=c["preview3d"], fg=c["muted"], font=self.theme.fonts["large"])
        self._fit_3d()
        for b in self.sw.values():
            b.configure(highlightbackground=c["border"], highlightcolor=c["accent"])
        if not self.theme.sv:
            for m in self.menus:
                m.configure(bg=c["bg"], fg=c["fg"])

    def _on_theme(self):
        self.theme.apply(self.v_theme.get())
        self.v_dark.set(self.theme.name == "dark")
        self._apply_widget_colours()
        self.s["theme"] = self.theme.name
        self._save_quietly()
        self.schedule(0)

    def _on_dark_switch(self):
        self.v_theme.set("dark" if self.v_dark.get() else "light")
        self._on_theme()

    def _insert(self, ch):
        self.e_text.insert(tk.INSERT, ch); self.e_text.focus_set()

    def show_about(self, modal=True):
        return AboutDialog(self.root, self.theme, modal=modal)

    # ---------------- fonts
    def _load_fonts_thread(self):
        try:
            # Old build folders (Make 3MF used to keep them) are cleaned up while the fonts load.
            sc.prune_work_dirs()
        except Exception:
            pass
        try:
            fonts = sc.list_fonts(extra_files=self.s.get("extra_fonts", []))
            self.q.put(("fonts", fonts))
        except Exception:
            self.q.put(("error", traceback.format_exc()))

    def _load_fonts_sync(self):
        self._set_fonts(sc.list_fonts(extra_files=self.s.get("extra_fonts", [])))

    def _set_fonts(self, fonts):
        self.fonts = fonts
        self.font_by_name = {f["name"]: f for f in fonts}
        self._fill_list()
        if not fonts:
            self.v_info.set("No fonts found. Install a font, or use Browse for font file…")
            return
        if self.s["font"] not in self.font_by_name:
            self.s["font"] = self._fallback_font_name()
            self.v_fontname.set(self.s["font"])
            self._fill_list()
        self.schedule(0)

    def _fallback_font_name(self):
        """Times New Roman when it is installed, otherwise another common serif, otherwise the first font."""
        return sc.preferred_font_name(self.fonts)

    def _fill_list(self):
        q = self.v_search.get().lower().strip()
        shown = [f for f in self.fonts if q in f["name"].lower()]
        self._shown = [f["name"] for f in shown]
        self.fontlist.set_fonts(shown, self.s["font"])

    def set_font(self, name):
        """The one place that changes the chosen font."""
        if not name or name not in self.font_by_name:
            return
        self.s["font"] = name
        self.v_fontname.set(name)
        self.fontlist.set_current(name)
        self.schedule()

    def _on_font_pick(self, name=None):
        self.set_font(name)

    def open_font_chooser(self, name=None):
        """The big picker: every font in its own typeface, with a preview of the wording."""
        if not self.fonts:
            messagebox.showinfo("Sign Maker", "No fonts found yet. Install a font, or use Browse…")
            return
        FontChooser(self.root, self)

    def browse_font(self):
        p = filedialog.askopenfilename(title="Choose a font file", filetypes=[("Fonts", "*.ttf *.otf *.ttc"), ("All files", "*.*")])
        if not p:
            return
        try:
            f = sc.font_from_file(os.path.normpath(p))
        except Exception as ex:
            messagebox.showerror("Sign Maker", "Could not read that font:\n%s" % ex); return
        self.fonts.insert(0, f); self.font_by_name[f["name"]] = f
        self.s.setdefault("extra_fonts", [])
        if f["path"] not in self.s["extra_fonts"]:
            self.s["extra_fonts"].append(f["path"])
        self.s["font"] = f["name"]; self.v_fontname.set(f["name"]); self.v_search.set(""); self._fill_list(); self.schedule()

    def current_font(self):
        f = self.font_by_name.get(self.s["font"])
        if f and self.v_bold.get():
            b = sc.bold_variant(f, self.fonts)
            if b:
                return b, ""
            return f, "  (no bold face for this font: using its normal face)"
        return f, ""

    # ---------------- params
    def params(self):
        p = dict(self.s)
        p["text"] = self.v_text.get()
        for k, _ in NUM_FIELDS:
            p[k] = float(self.v_num[k].get().replace(",", "."))
        p["auto_size"] = self.v_auto.get()
        p["text_size"] = float(self.v_size.get().replace(",", ".") or 8)
        p["bold"] = self.v_bold.get(); p["style"] = self.v_style.get(); p["stl"] = self.v_stl.get()
        for k, v in (("plate_color", self.v_pc), ("text_color", self.v_tc)):
            c = v.get().strip()
            if not (len(c) == 7 and c.startswith("#") and all(x in "0123456789abcdefABCDEF" for x in c[1:])):
                raise ValueError("Colour must look like #RRGGBB")
            p[k] = c.upper()
        if p["length"] <= 0 or p["height"] <= 0 or p["thickness"] <= 0 or p["raise"] <= 0:
            raise ValueError("Sizes must be above zero")
        if p["margin"] * 2 >= min(p["length"], p["height"]):
            raise ValueError("Margin is too big for the plate")
        if p["style"] == "engraved" and p["thickness"] <= 0.3:
            raise ValueError("Plate is too thin to engrave")
        return p

    @staticmethod
    def design_key(p, f):
        return json.dumps([p.get(k) for k in MODEL_KEYS] + [f.get("path"), f.get("name")], ensure_ascii=False)

    def schedule(self, ms=150):
        if self._after:
            self.root.after_cancel(self._after)
        self._after = self.root.after(ms, self.update_preview)

    def update_preview(self):
        self._after = None
        for k, v in (("plate_color", self.v_pc), ("text_color", self.v_tc)):
            try:
                self.sw[str(v)].config(bg=v.get(), activebackground=v.get())
            except Exception:
                pass
        self.e_size.config(state="disabled" if self.v_auto.get() else "normal")
        if not self.fonts:
            return
        try:
            p = self.params()
        except Exception as ex:
            self.v_info.set("⚠ " + str(ex)); self.l_info.configure(style="Warn.TLabel"); return
        f, note = self.current_font()
        if not f:
            self.v_info.set("Pick a font"); return
        try:
            w = self.c2d.winfo_width()
            self._2d_limit = self._limit_2d(p)
            w = self._target_2d(w)
            self._w2d = w
            bg = tuple(int(self.theme.c["preview"][i:i + 2], 16) for i in (1, 3, 5))
            img, info = sc.preview_image(p, f, width_px=w, bg=bg)
        except Exception as ex:
            self.v_info.set("⚠ Preview failed: %s" % ex); self.l_info.configure(style="Warn.TLabel"); return
        self._img2d = ImageTk.PhotoImage(img); self.c2d.config(image=self._img2d)
        miss = sc.missing_glyphs(f, p["text"])
        msg, warn = "", False
        if info.get("cap_mm"):
            msg = "Text %.1f × %.1f mm  ·  cap height %.2f mm" % (info["text_w"], info["text_h"], info["cap_mm"])
            if not info.get("fits"):
                msg += "   ⚠ text is bigger than the plate inside the margins"; warn = True
        if miss:
            msg += "   ⚠ font has no glyph for: " + " ".join(miss); warn = True
        self.v_info.set(msg + note)
        self.l_info.configure(style="Warn.TLabel" if warn else "Info.TLabel")
        self.save_settings_soon(p)
        self._design_changed(p, f)

    def _limit_2d(self, p):
        """Widest the 2D preview may be, so a tall plate does not push the rest off a short screen."""
        try:
            L, H = float(p["length"]), float(p["height"])
            if L > 0 and H > 0:
                return max(200, min(1100, int((self._max2d_h - 60) * L / H) + 60))
        except (TypeError, ValueError, KeyError):
            pass
        return 1100

    def _target_2d(self, avail):
        w = 760 if avail < 50 else max(200, min(avail, 1100))
        return max(200, min(w, self._2d_limit))

    def _on_2d_resize(self, e):
        # Redraw only when the picture would really change size, and only once a resize settles.
        if abs(self._target_2d(e.width) - self._w2d) <= 2:
            return
        if self._2d_after:
            self.root.after_cancel(self._2d_after)
        self._2d_after = self.root.after(180, self._redraw_2d)

    def _redraw_2d(self):
        """Re-render the 2D picture for a new size. The design is unchanged: no info, save or 3D work."""
        self._2d_after = None
        if not self.fonts or self._after:          # a full update is already on its way
            return
        try:
            p = self.params(); f, _ = self.current_font()
            if not f:
                return
            w = self._target_2d(self.c2d.winfo_width())
            if abs(w - self._w2d) <= 2:
                return
            bg = tuple(int(self.theme.c["preview"][i:i + 2], 16) for i in (1, 3, 5))
            img, _ = sc.preview_image(p, f, width_px=w, bg=bg)
        except Exception:
            self.schedule(0); return
        self._w2d = w
        self._img2d = ImageTk.PhotoImage(img); self.c2d.config(image=self._img2d)

    # ---------------- fitting the screen
    def _on_wheel(self, e):
        w = self.root.winfo_containing(e.x_root, e.y_root)
        if w is None or not self.scroll.contains(w):
            return
        if str(w).startswith(str(self._lbframe)):
            return                     # the font list scrolls itself
        self.scroll.scroll(self._wheel_units(e))

    def _on_wheel_break(self, e):
        self.scroll.scroll(self._wheel_units(e))
        return "break"

    @staticmethod
    def _wheel_units(e):
        if getattr(e, "num", None) == 4:
            return -1
        if getattr(e, "num", None) == 5:
            return 1
        d = getattr(e, "delta", 0) or 0
        if sys.platform == "darwin" and abs(d) < 120:
            return -d
        n = int(-d / 120)
        return n or (-1 if d > 0 else 1 if d < 0 else 0)

    def _on_root_configure(self, e):
        if e.widget is not self.root:
            return
        size = (e.width, e.height)
        if self._last_geom is not None and self._last_geom[0] == size:
            # Only moved. Re-check (once it settles) only if that may have put it on another monitor.
            if self._layout_after is None:
                self._layout_after = self.root.after(400, self._check_monitor)
            return
        self._last_geom = (size, None)
        if self._layout_after:
            self.root.after_cancel(self._layout_after)
        self._layout_after = self.root.after(200, self._update_layout)

    def _check_monitor(self):
        self._layout_after = None
        try:
            wa = work_area(self.root)
        except Exception:
            return
        if wa != self._last_work:
            self._update_layout()

    def _update_layout(self):
        """Pick the normal or compact layout from the screen the window is on and the window size.
        Moving to another monitor or resizing re-checks it. Only sizes change, never the design,
        so this does not start a 3D build."""
        self._layout_after = None
        try:
            scale = screen_scale(self.root)
            self._last_work = work_area(self.root)
            work_h = self._last_work[3] / scale
            win_h = self.root.winfo_height() / scale if self.root.winfo_ismapped() else None
        except Exception:
            return
        if self._compact:
            want = work_h < COMPACT_BELOW + 20 or (win_h is not None and win_h < 820)
        else:
            want = work_h < COMPACT_BELOW or (win_h is not None and win_h < 780)
        tight = want and work_h < 660
        if want != self._compact or (want and tight != self._tight):
            self._tight = tight
            self._set_compact(want)

    def _set_compact(self, compact):
        self._compact = compact
        self.theme.compact = compact
        self.theme.style.configure("TLabelframe", padding=(12, 4, 12, 7) if compact else (14, 8, 14, 12))
        self._hd.configure(padding=(18, 5, 18, 5) if compact else (18, 10, 18, 10))
        self._body.configure(padding=(12, 6, 12, 2) if compact else (14, 10, 14, 4))
        for c in self._gap_cards:
            c.grid_configure(pady=(0, 4) if compact else (0, 8))
        self._p3.grid_configure(pady=(4, 4) if compact else (8, 8))
        self.fontlist.set_rows(4 if compact else 6)
        self.f3d.configure(height=180 if compact else 320)
        old = self._max2d_h
        self._max2d_h = (120 if self._tight else 170) if compact else 360
        if compact and self._tight:
            self._l_savehint.grid_remove()       # the folder is in the field above anyway
        else:
            self._l_savehint.grid()
        self.root.update_idletasks()
        self.scroll.refresh()
        if old != self._max2d_h and self.fonts:
            self.schedule(0)

    def save_settings_soon(self, p):
        for k in ["text", "length", "height", "thickness", "raise", "margin", "corner", "spacing", "auto_size", "text_size",
                  "bold", "style", "plate_color", "text_color", "stl"]:
            self.s[k] = p[k]
        self._save_quietly()

    def _save_quietly(self):
        try:
            sc.save_settings(self.s)
            self._save_failed = False
        except Exception as ex:
            # Say it once: silently losing the settings is worse than a line in the status bar.
            if not getattr(self, "_save_failed", False):
                self._save_failed = True
                self.v_status.set("Could not save settings to %s: %s" % (sc.DATA_DIR, ex))

    # ---------------- 3D preview
    def _cli_path(self):
        if self._cli is None:
            try:
                self._cli = sc.find_cli(self.s)
            except FileNotFoundError:
                self._cli = ""
        return self._cli

    def _set_3d_state(self, state, detail=""):
        """idle | busy | ok | stale | off | nocli | fail"""
        self._3d_state = state
        texts = {
            "idle": ("", "Muted.TLabel"),
            "busy": ("Updating 3D preview…", "Busy.TLabel"),
            "ok": ("✓ Up to date", "Ok.TLabel"),
            "stale": ("Changed since this preview. Press Refresh (F5).", "Warn.TLabel"),
            "off": ("Auto preview is off. Press Refresh (F5).", "Muted.TLabel"),
            "nocli": ("SolidCraft not found: File › SolidCraft path…", "Warn.TLabel"),
            "fail": ("⚠ 3D preview failed" + (": " + detail if detail else ""), "Warn.TLabel"),
        }
        text, style = texts[state]
        self.v_3dstate.set(text[:90]); self.l_3dstate.configure(style=style)
        if state == "busy":
            if not self.pb3d.winfo_manager():
                self.pb3d.pack(side="right", padx=(0, 10)); self.pb3d.start(12)
        elif self.pb3d.winfo_manager():
            self.pb3d.stop(); self.pb3d.pack_forget()
        if self._im3d is None:
            if state == "nocli":
                ph = "Install SolidCraft to see the 3D preview here.\nThe 2D preview above works without it."
            elif state == "busy":
                ph = "Building the 3D preview in SolidCraft…"
            elif state == "fail":
                ph = "The 3D preview could not be built.\nSee the message above."
            elif self.v_auto3d.get():
                ph = "The 3D preview appears here."
            else:
                ph = "Press Refresh 3D preview to see the sign in 3D."
            self._fit_key = None; self.c3d.configure(image="", text=ph)

    def _design_changed(self, p, f):
        key = self.design_key(p, f)
        self._cur = (p, f, key)
        if self._after3d:
            self.root.after_cancel(self._after3d); self._after3d = None
        if key == self._shown_key:
            self._cancel_3d()
            self._set_3d_state("ok"); return
        if self._job is not None and self._job.key == key:
            return  # already building exactly this
        self._cancel_3d()
        if not self._cli_path():
            self._set_3d_state("nocli"); return
        if self.v_auto3d.get():
            self._set_3d_state("busy")
            self._after3d = self.root.after(AUTO_3D_DELAY_MS, self.refresh_3d)
        else:
            self._set_3d_state("stale" if self._im3d is not None else "off")

    def _cancel_3d(self):
        if self._job is not None:
            self._job.cancel.set()
            self._job = None
            self._gen += 1

    def refresh_3d(self, manual=False):
        """Build the 3D preview for the current design in a background thread."""
        self._after3d = None
        if manual:
            self._sync_paths()
            self._cli = None
            self.update_preview_now()
            if self._after3d:
                self.root.after_cancel(self._after3d); self._after3d = None
        if self._cur is None:
            return
        if not self._cli_path():
            self._set_3d_state("nocli")
            if manual:
                messagebox.showwarning("Sign Maker", "solidcraft-cli was not found.\n\nUse File › SolidCraft path… "
                                                     "(or Browse next to solidcraft-cli) to choose it.")
            return
        p, f, key = self._cur
        if not p["text"].strip():
            self._set_3d_state("idle"); return
        if key == self._shown_key and not manual:
            self._set_3d_state("ok"); return
        if self._job is not None and self._job.key == key:
            return
        self._cancel_3d()
        self._gen += 1
        job = types.SimpleNamespace(gen=self._gen, key=key, cancel=threading.Event())
        self._job = job
        self._set_3d_state("busy")
        p = dict(p, stl=False)  # a preview never needs the STLs
        threading.Thread(target=self._worker3d, args=(job, p, f, self._snap_size()), daemon=True).start()

    def update_preview_now(self):
        if self._after:
            self.root.after_cancel(self._after)
        self.update_preview()

    def _snap_size(self):
        """The 3D preview is rendered at the size the pane shows it, not at a fixed 1200x700.

        SolidCraft re-evaluates the whole design to make a snapshot, and the picture is scaled
        down to the pane anyway, so asking for the displayed size gives the same view for less
        work. Call this on the Tk thread, before starting the build.
        """
        try:
            w = int(self.c3d.winfo_width())
        except Exception:
            w = 0
        if w < 320:                       # not laid out yet: keep the old default
            return (1200, 700)
        w = max(480, min(1200, w))
        return (w, max(1, round(w * 700 / 1200)))

    def _worker3d(self, job, p, f, snap=(1200, 700)):
        work = None
        try:
            work = sc.new_work_dir("preview-")
            res = sc.build_sign(p, f, work=work, log=lambda m: self.q.put(("p3d_status", (job.gen, m))),
                                cancel=job.cancel)
            im = None
            if res.get("snapshot"):
                im = self._load_snapshot(res["snapshot"])
            tb = res["text_bbox"]
            summary = "Plate %.1f × %.1f × %.2f mm  ·  text %.2f × %.2f mm, top at %.2f mm, cap height %.2f mm" % (
                p["length"], p["height"], p["thickness"], tb["max"][0] - tb["min"][0], tb["max"][1] - tb["min"][1],
                tb["max"][2], res["cap"])
            self.q.put(("p3d_done", (job.gen, job.key, im, summary)))
        except sc.Cancelled:
            pass
        except Exception as ex:
            self.q.put(("p3d_fail", (job.gen, str(ex))))
        finally:
            if work:
                shutil.rmtree(work, ignore_errors=True)

    @staticmethod
    def _load_snapshot(path):
        """Open a SolidCraft snapshot and find its backdrop (done in the worker thread)."""
        im = Image.open(path); im.load(); im = im.convert("RGB")
        try:
            mask = sc.snapshot_background_mask(im)
        except Exception:
            mask = None
        return im, mask

    def _show_3d(self, im):
        self._im3d, self._mask3d = im
        self._fit_key = None
        self._fit_3d()

    def _fit_3d(self):
        self._fit_after = None
        if self._im3d is None:
            return
        w = max(300, self.f3d.winfo_width() - 8); h = max(200, self.f3d.winfo_height() - 8)
        key = (id(self._im3d), self.theme.name, self.theme.c["preview3d"], w, h)
        if key == self._fit_key:
            return                                  # already showing exactly this
        self._fit_key = key
        im = self._im3d
        if self.theme.name == "dark" and self._mask3d is not None:
            if self._dark3d is None or self._dark3d[0] is not im or self._dark3d[1] != self.theme.c["preview3d"]:
                try:
                    self._dark3d = (im, self.theme.c["preview3d"],
                                    sc.recolour_snapshot(im, self._mask3d, self.theme.c["preview3d"]))
                except Exception:
                    self._dark3d = (im, self.theme.c["preview3d"], im)
            im = self._dark3d[2]
        im = im.copy(); im.thumbnail((w, h), Image.Resampling.LANCZOS)
        self._img3d = ImageTk.PhotoImage(im)
        self.c3d.config(image=self._img3d, text="")

    def _on_3d_resize(self, e=None):
        if self._im3d is None:
            return
        if self._fit_after:
            self.root.after_cancel(self._fit_after)
        self._fit_after = self.root.after(180, self._fit_3d)

    def _on_auto3d(self):
        self.s["auto_preview"] = bool(self.v_auto3d.get())
        self._save_quietly()
        if self.v_auto3d.get():
            self.update_preview_now()
        else:
            if self._after3d:
                self.root.after_cancel(self._after3d); self._after3d = None
            if self._job is None and self._3d_state == "busy":
                self._set_3d_state("stale" if self._im3d is not None else "off")
            elif self._3d_state not in ("busy", "ok", "nocli"):
                self._set_3d_state("stale" if self._im3d is not None else "off")

    # ---------------- colours / favourites
    def pick_colour(self, var):
        c = colorchooser.askcolor(color=var.get(), title="Choose colour")
        if c and c[1]:
            var.set(c[1].upper())

    def swap_colours(self):
        a, b = self.v_pc.get(), self.v_tc.get(); self.v_pc.set(b); self.v_tc.set(a)

    def _refresh_favs(self):
        self.cb_fav["values"] = [f["label"] for f in self.s.get("favourites", [])]

    def use_fav(self):
        i = self.cb_fav.current()
        if i < 0:
            return
        f = self.s["favourites"][i]
        self.v_text.set(f["text"])
        if f.get("font") in self.font_by_name:
            self.s["font"] = f["font"]; self.v_fontname.set(f["font"]); self._fill_list()
        for k, var in (("plate_color", self.v_pc), ("text_color", self.v_tc)):
            if f.get(k):
                var.set(f[k])
        self.schedule()

    def add_fav(self):
        lab = "%s (%s)" % (self.v_text.get(), self.s["font"])
        self.s.setdefault("favourites", []).append({"label": lab, "text": self.v_text.get(), "font": self.s["font"],
                                                     "plate_color": self.v_pc.get(), "text_color": self.v_tc.get()})
        self._save_quietly(); self._refresh_favs(); self.cb_fav.set(lab)

    def del_fav(self):
        i = self.cb_fav.current()
        if i >= 0:
            del self.s["favourites"][i]; self._save_quietly(); self._refresh_favs(); self.cb_fav.set("")

    # ---------------- make 3MF
    def make(self):
        if self.busy:
            return
        self.bmk_box.steam(4000)
        self._sync_paths()
        self._cli = None
        try:
            sc.find_cli(self.s)
        except FileNotFoundError as ex:
            messagebox.showwarning("Sign Maker", str(ex) + "\n\nUse Browse next to solidcraft-cli to choose the file.")
            self.browse_cli()
            try:
                sc.find_cli(self.s)
            except FileNotFoundError:
                return
        try:
            p = self.params()
        except Exception as ex:
            messagebox.showwarning("Sign Maker", str(ex)); return
        f, _ = self.current_font()
        if not f:
            return
        self.busy = True
        self._sparkle_gen += 1               # stop a twinkle that is still running
        self.bmk.config(state="disabled", text="Making…")
        threading.Thread(target=self._worker, args=(p, f, self.design_key(p, f), self._snap_size()), daemon=True).start()

    # The twinkle below cycles glyphs rather than growing the label, so the "Open folder"
    # button beside it does not shift while it plays.
    SPARKLE_MS = 140
    SPARKLE_FRAMES = ("✦ Saved!", "✧ Saved!", "✦ Saved!", "✧ Saved!")

    def _sparkle_saved(self):
        """Twinkle the Make 3MF button once the file is on disk, then put its label back.

        Decoration only: if anything here fails, the save the user just got is unaffected.
        """
        self._sparkle_gen += 1
        run = self._sparkle_gen
        frames = self.SPARKLE_FRAMES + ("Make 3MF",)

        def step(i):
            if run != self._sparkle_gen:
                return                       # a newer twinkle, or a new build, took over
            try:
                if self.busy:
                    return                   # "Making…" owns the button now
                self.bmk.config(text=frames[i])
            except tk.TclError:
                return                       # the window closed mid-twinkle
            if i + 1 < len(frames):
                self.root.after(self.SPARKLE_MS, lambda: step(i + 1))

        step(0)

    def _worker(self, p, f, key, snap=(1200, 700)):
        log = lambda m: self.q.put(("status", m))
        work = None
        try:
            work = sc.new_work_dir("make-")
            res = sc.build_sign(p, f, work=work, log=log, snapshot_size=snap)
            out = sc.save_outputs(res, p, root=sc.output_root(self.s), log=log)
            im = None
            if res.get("snapshot"):
                im = self._load_snapshot(res["snapshot"])
            self.q.put(("done", (res, out, im, key, p)))
        except Exception as ex:
            self.q.put(("fail", str(ex)))
        finally:
            # The saved files are copies; the build folder is scratch and can go now.
            if work:
                shutil.rmtree(work, ignore_errors=True)

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                self._handle(kind, data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _handle(self, kind, data):
        if kind == "fonts":
            self._set_fonts(data)
        elif kind == "status":
            self.v_status.set(data)
        elif kind == "error":
            self.v_info.set("Font list failed: " + data[-300:])
        elif kind == "update":
            self._update_result(*data)
        elif kind == "p3d_status":
            gen, msg = data
            if gen == self._gen:
                self.v_status.set("3D preview: " + msg)
        elif kind == "p3d_done":
            gen, key, im, summary = data
            if gen != self._gen:
                return  # an older design: ignore
            self._job = None
            self._shown_key = key
            if im is not None:
                self._show_3d(im)
            self.v_status.set(summary)
            cur = self._cur[2] if self._cur else None
            self._set_3d_state("ok" if cur == key else "stale")
        elif kind == "p3d_fail":
            gen, msg = data
            if gen != self._gen:
                return
            self._job = None
            first = next((ln for ln in msg.splitlines() if ln.strip()), "error")
            self._set_3d_state("fail", first)
            self.v_status.set("3D preview failed: " + " ".join(msg.split())[-300:])
        elif kind == "fail":
            self.busy = False; self.bmk.config(state="normal", text="Make 3MF")
            self.v_status.set("Failed"); messagebox.showerror("Sign Maker", data[-1500:])
        elif kind == "done":
            self.busy = False; self.bmk.config(state="normal", text="Make 3MF")
            res, out, im, key, p = data
            cur = self._cur[2] if self._cur else None
            if im is not None and key == cur:
                self._cancel_3d()
                self._shown_key = key
                self._show_3d(im)
                self._set_3d_state("ok")
            tb = res["text_bbox"]
            msg = "Plate %.1f × %.1f × %.2f mm  ·  text %.2f × %.2f mm, cap height %.2f mm" % (
                p["length"], p["height"], p["thickness"], tb["max"][0] - tb["min"][0], tb["max"][1] - tb["min"][1],
                res["cap"])
            self.last_folder = out["folder"]; self.bop.config(state="normal")
            self.v_status.set("Saved %s.3mf in %s  ·  %s" % (out["base"], out["folder"], msg))
            if out.get("3mf") and os.path.exists(out["3mf"]):
                self._sparkle_saved()

    # ---------------- folders and paths
    @staticmethod
    def _open_path(path):
        if hasattr(os, "startfile"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def open_folder(self):
        if self.last_folder and os.path.isdir(self.last_folder):
            self._open_path(self.last_folder)

    def open_signs_root(self):
        root = (self.v_out.get() or "").strip() or sc.default_output_dir()
        try:
            os.makedirs(root, exist_ok=True)
            self._open_path(root)
        except Exception as ex:
            messagebox.showerror("Sign Maker", "Could not open %s:\n%s" % (root, ex))

    def _update_save_hint(self):
        sep = "\\" if os.name == "nt" else "/"
        root = (self.v_out.get() or "").strip() or sc.default_output_dir()
        self.v_savehint.set("Each sign is saved in " + root + sep + "<wording>")

    def _refresh_cli_field(self):
        self._cli = None
        try:
            self.v_cli.set(sc.find_cli(self.s))
        except FileNotFoundError:
            self.v_cli.set((self.s.get("cli_path") or "").strip())

    def _sync_paths(self):
        """Remember the CLI and the save folder in the settings file."""
        out = self.v_out.get().strip()
        self.s["output_dir"] = out if out and os.path.normcase(out) != os.path.normcase(sc.default_output_dir()) else ""
        cli = self.v_cli.get().strip()
        if cli != (self.s.get("cli_path") or ""):
            self._cli = None
        self.s["cli_path"] = cli
        self._save_quietly()

    def browse_cli(self):
        if os.name == "nt":
            types_ = [("solidcraft-cli", "solidcraft-cli.exe"), ("All files", "*.*")]
        else:
            types_ = [("All files", "*")]
        p = filedialog.askopenfilename(title="Locate solidcraft-cli", filetypes=types_)
        if not p:
            return False
        p = os.path.normpath(p)
        if not os.path.isfile(p):
            messagebox.showerror("Sign Maker", "That file does not exist.")
            return False
        self.v_cli.set(p)
        self._sync_paths()
        self._cli = None
        self.v_status.set("Using SolidCraft: " + p)
        self._shown_key = None
        self.update_preview_now()
        return True

    def browse_output(self):
        initial = self.v_out.get().strip() or sc.default_output_dir()
        if not os.path.isdir(initial):
            parent = os.path.dirname(initial)
            initial = parent if os.path.isdir(parent) else os.path.expanduser("~")
        p = filedialog.askdirectory(title="Folder for saved signs", initialdir=initial)
        if not p:
            return
        self.v_out.set(os.path.normpath(p))
        self._sync_paths()

    def _maybe_prompt_cli(self):
        """First launch with no SolidCraft CLI: explain, then offer Browse. 2D preview still works."""
        self._refresh_cli_field()
        path = self._cli_path()
        if path:
            self.v_status.set("SolidCraft: " + path)
            return
        cli_name = "solidcraft-cli.exe" if os.name == "nt" else "solidcraft-cli"
        self.v_status.set("SolidCraft CLI not found yet. 2D preview works; Browse to " + cli_name + " for 3D and 3MF.")
        self._set_3d_state("nocli")
        if self.s.get("cli_prompted"):
            return
        self.s["cli_prompted"] = True
        self._save_quietly()
        messagebox.showinfo(
            "Sign Maker",
            "Sign Maker draws the 2D preview by itself.\n"
            "The 3D preview and the 3MF file are built by SolidCraft.\n\n"
            "solidcraft-cli was not found. Install SolidCraft from\n"
            "https://github.com/tangency-labs/solidcraft/releases\n"
            "Windows: MSI or portable zip (not the single-file .exe).\n"
            "macOS: the solidcraft-cli zip, or SolidCraft.app.\n"
            "Linux: .deb, .rpm or .tar.gz, or an extracted AppImage.\n"
            "Then press Browse.\n\n"
            "Finished signs are saved under Documents/Sign Maker/Signs.\n"
            "You can change that folder here too.")
        self.browse_cli()

    # ---------------- updates
    def check_updates(self):
        self.v_status.set("Checking GitHub for a newer Sign Maker…")
        threading.Thread(target=self._update_thread, daemon=True).start()

    def _update_thread(self):
        try:
            import urllib.request
            req = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json",
                                                              "User-Agent": "SignMaker/" + __version__})
            with urllib.request.urlopen(req, timeout=8) as r:
                tag = json.load(r).get("tag_name", "")
            self.q.put(("update", (tag, None)))
        except Exception as ex:
            self.q.put(("update", ("", str(ex))))

    def _update_result(self, tag, err):
        self.v_status.set("")
        if err or not tag:
            if messagebox.askyesno("Sign Maker", "Could not check for updates (%s).\n\nOpen the releases page?" % (err or "no release found")):
                open_url(RELEASES_URL)
            return
        if version_tuple(tag) > version_tuple(__version__):
            if messagebox.askyesno("Sign Maker", "Sign Maker %s is available (you have %s).\n\nOpen the download page?"
                                   % (tag.lstrip("v"), __version__)):
                open_url(RELEASES_URL + "/latest")
        else:
            messagebox.showinfo("Sign Maker", "You have the latest Sign Maker (%s)." % __version__)

    # ---------------- close
    def on_close(self):
        self._cancel_3d()
        try:
            self._sync_paths()
            self.save_settings_soon(self.params())
        except Exception:
            pass
        self.root.destroy()


def selftest():
    log = ["version: " + __version__, "theme: " + ("sv-ttk" if sv_ttk else "plain ttk")]
    os.makedirs(sc.DATA_DIR, exist_ok=True)
    root = tk.Tk(); root.withdraw()
    app = App(root, selftest=True)
    log.append("ui font: " + app.theme.family)
    log.append("fonts: %d" % len(app.fonts))
    pairs = (
        ("serif", sc.SERIF_FONT_NAMES, "Telefón", "selftest_serif.png"),
        ("sans", sc.SANS_FONT_NAMES, "TELEPHONE", "selftest_sans.png"),
    )
    for label, names, text, fname in pairs:
        f = sc.match_font(app.fonts, names)
        log.append("%s -> %s" % (label, ("%s (%s)" % (f["name"], f["path"])) if f else "MISSING"))
        if f:
            p = sc.load_settings(); p["text"] = text
            img, info = sc.preview_image(p, f)
            img.save(os.path.join(sc.DATA_DIR, fname))
            log.append("  preview ok %s cap %.2f fits %s" % (img.size, info["cap_mm"], info["fits"]))
    if app.fonts and not any(line.startswith("  preview ok") for line in log):
        f = app.font_by_name.get(app.s.get("font")) or app.fonts[0]
        p = sc.load_settings(); p["text"] = "Telefón"
        img, info = sc.preview_image(p, f)
        img.save(os.path.join(sc.DATA_DIR, "selftest_fallback.png"))
        log.append("fallback %s preview ok %s cap %.2f fits %s" % (f["name"], img.size, info.get("cap_mm") or 0, info.get("fits")))
    root.update(); app.update_preview(); log.append("info: " + app.v_info.get())
    # 3D preview without SolidCraft must not crash, only say so
    app._cli = ""
    app.v_auto3d.set(True); app._shown_key = None
    app.update_preview(); app.refresh_3d()
    log.append("3d without cli: " + app._3d_state)
    if app.fonts and app._3d_state != "nocli":
        raise RuntimeError("3D state without CLI is %s" % app._3d_state)
    # theme switch both ways, and the About window
    for name in ("dark", "light"):
        app.v_theme.set(name); app._on_theme(); root.update()
    # short-screen layout: compact sizes, and the left column scrolls to the colours
    app._set_compact(True)
    root.deiconify()          # a withdrawn window ignores geometry requests (seen on Windows)
    root.update()
    root.geometry("1000x640")

    def settle(seconds):
        """Pump the event loop: layout and scrollbar changes are debounced until a resize lands."""
        end = time.time() + seconds
        while time.time() < end:
            root.update(); time.sleep(0.02)

    settle(1.0)
    if not app.scroll.needed():
        # How much fits in 640 px depends on the fonts and the display scaling, which differ
        # per machine (this failed on the Windows runners). Make the window short enough that
        # the column must scroll, instead of assuming 640 px is short everywhere.
        for height in (560, 480, 420, 360, 300):
            root.geometry("1000x%d" % height)
            settle(0.5)
            if app.scroll.needed():
                break
    if not app.scroll.needed() or not app.scroll.vsb.winfo_manager():
        raise RuntimeError("left column does not scroll on a short window (%s, needs scrolling: %s, scrollbar: %s)"
                           % (root.geometry(), app.scroll.needed(), bool(app.scroll.vsb.winfo_manager())))
    app.scroll.canvas.yview_moveto(1.0); root.update()
    if app.scroll.canvas.yview()[1] < 0.999:
        raise RuntimeError("left column cannot reach the bottom (%.3f at %s)"
                           % (app.scroll.canvas.yview()[1], root.geometry()))
    log.append("compact layout: scrolls %.2f-%.2f, font rows %s" % (app.scroll.canvas.yview() + (app.fontlist.rows,)))
    app._set_compact(False); root.geometry(""); root.update(); root.withdraw()
    # the Make button twinkles after a save and must come back to its own label
    app._sparkle_saved(); settle(1.0)
    if app.bmk.cget("text") != "Make 3MF":
        raise RuntimeError("Make 3MF label did not come back: %r" % app.bmk.cget("text"))
    log.append("twinkle: back to %r" % app.bmk.cget("text"))
    # pressing Make starts the steam burst, and it clears itself afterwards
    app.bmk_box.steam(250)
    if not app.bmk_box._active:
        raise RuntimeError("Make button steam did not start")
    settle(0.75)
    if app.bmk_box._active or any(app.bmk_box.itemcget(i, "state") != "hidden" for i in app.bmk_box._items):
        raise RuntimeError("Make button steam did not stop")
    log.append("steam: started and stopped")
    about = app.show_about(modal=False); root.update()
    log.append("about: %dx%d" % (about.winfo_width(), about.winfo_height()))
    about.close()
    try:
        log.append("cli: " + sc.find_cli())
    except Exception as ex:
        log.append("cli: not found (" + str(ex).split("\n")[0] + ")")
    expect = os.path.join(os.path.expanduser("~"), "Documents", "Sign Maker", "Signs")
    log.append("output: " + sc.default_output_dir())
    log.append("config: " + sc.DATA_DIR)
    if os.path.normcase(os.path.abspath(sc.default_output_dir())) != os.path.normcase(os.path.abspath(expect)):
        raise RuntimeError("default output folder is %s" % sc.default_output_dir())
    root.destroy()
    out = os.path.join(sc.DATA_DIR, "selftest.log")
    os.makedirs(sc.DATA_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\nSELFTEST OK\n")
    print("\n".join(log)); print("SELFTEST OK")


if __name__ == "__main__":
    if "--version" in sys.argv:
        print(__version__); sys.exit(0)
    if "--selftest" in sys.argv:
        try:
            selftest()
        except Exception:
            os.makedirs(sc.DATA_DIR, exist_ok=True)
            open(os.path.join(sc.DATA_DIR, "selftest.log"), "w", encoding="utf-8").write(traceback.format_exc())
            raise
        sys.exit(0)
    root = tk.Tk()
    root.withdraw()                      # stay hidden until it is sized and centred
    remember_screen_dpi(root)
    try:
        root.tk.call("tk", "scaling", 1.3)
    except Exception:
        pass
    app = App(root)
    place_main_window(root)
    if "--show-about" in sys.argv:  # used for README screenshots
        root.after(1500, app.show_about)
    root.mainloop()
