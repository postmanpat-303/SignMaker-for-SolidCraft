# -*- coding: utf-8 -*-
"""Sign Maker - two-colour 3D-print signs with SolidCraft. Author: Del (postmanpat)."""
import os, sys, threading, queue, traceback, subprocess, json
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox
from PIL import Image, ImageTk
import signcore as sc

NUM_FIELDS = [("length", "Plate length (mm)"), ("height", "Plate height (mm)"), ("thickness", "Plate thickness (mm)"),
              ("raise", "Text raise / engrave depth (mm)"), ("margin", "Margin (mm)"), ("corner", "Corner radius (mm)"),
              ("spacing", "Extra letter spacing (mm)")]

def asset_path(*parts):
    """A file shipped with the app: next to the source, or inside a PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)

def apply_window_icon(root):
    """Window and taskbar icon. PNG on every OS; the .ico is also set on Windows."""
    png = asset_path("assets", "icon.png")
    if os.path.isfile(png):
        try:
            img = Image.open(png)
            img.thumbnail((256, 256), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
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

class App:
    def __init__(self, root, selftest=False):
        self.root = root
        apply_window_icon(root)
        self.s = sc.load_settings()
        self.fonts, self.font_by_name = [], {}
        self.q = queue.Queue()
        self.busy = False
        self.last_folder = None
        self._after = None
        root.title("Sign Maker - SolidCraft two-colour signs")
        root.minsize(1100, 780)
        self._build_ui()
        if selftest:
            self._load_fonts_sync()
        else:
            threading.Thread(target=self._load_fonts_thread, daemon=True).start()
            root.after(100, self._poll)
            root.after(400, self._maybe_prompt_cli)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI
    def _build_ui(self):
        r = self.root
        left = ttk.Frame(r, padding=8); left.grid(row=0, column=0, sticky="nsw")
        right = ttk.Frame(r, padding=8); right.grid(row=0, column=1, sticky="nsew")
        r.columnconfigure(1, weight=1); r.rowconfigure(0, weight=1)

        ttk.Label(left, text="Wording").grid(row=0, column=0, sticky="w")
        self.v_text = tk.StringVar(value=self.s["text"])
        e = ttk.Entry(left, textvariable=self.v_text, width=38, font=("Segoe UI", 12)); e.grid(row=1, column=0, columnspan=3, sticky="we")
        self.e_text = e
        acc = ttk.Frame(left); acc.grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 6))
        for ch in "áéíóúÁÉÍÓÚ⁊":
            ttk.Button(acc, text=ch, width=2, command=lambda c=ch: self._insert(c)).pack(side="left")

        ttk.Label(left, text="Font  (search)").grid(row=3, column=0, sticky="w")
        self.v_search = tk.StringVar()
        ttk.Entry(left, textvariable=self.v_search, width=24).grid(row=3, column=1, columnspan=2, sticky="we")
        fl = ttk.Frame(left); fl.grid(row=4, column=0, columnspan=3, sticky="we")
        self.lb = tk.Listbox(fl, height=10, width=44, exportselection=False)
        sb = ttk.Scrollbar(fl, command=self.lb.yview); self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True); sb.pack(side="left", fill="y")
        self.lb.bind("<<ListboxSelect>>", self._on_font_pick)
        fr = ttk.Frame(left); fr.grid(row=5, column=0, columnspan=3, sticky="we", pady=2)
        self.v_fontname = tk.StringVar(value=self.s["font"])
        ttk.Label(fr, textvariable=self.v_fontname, foreground="#1f3a93").pack(side="left")
        ttk.Button(fr, text="Browse for font file…", command=self.browse_font).pack(side="right")
        self.v_bold = tk.BooleanVar(value=self.s.get("bold", False))
        ttk.Checkbutton(left, text="Bold (uses the family's bold face)", variable=self.v_bold).grid(row=6, column=0, columnspan=3, sticky="w")

        nf = ttk.LabelFrame(left, text="Sizes", padding=6); nf.grid(row=7, column=0, columnspan=3, sticky="we", pady=4)
        self.v_num = {}
        for i, (k, lab) in enumerate(NUM_FIELDS):
            ttk.Label(nf, text=lab).grid(row=i // 2, column=(i % 2) * 2, sticky="e", padx=(4, 2))
            v = tk.StringVar(value=str(self.s[k])); self.v_num[k] = v
            ttk.Entry(nf, textvariable=v, width=7).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w")
        row = (len(NUM_FIELDS) + 1) // 2
        self.v_auto = tk.BooleanVar(value=self.s.get("auto_size", True))
        ttk.Checkbutton(nf, text="Auto-fit text size", variable=self.v_auto).grid(row=row, column=0, columnspan=2, sticky="w")
        ttk.Label(nf, text="Cap height (mm)").grid(row=row, column=2, sticky="e")
        self.v_size = tk.StringVar(value=str(self.s.get("text_size", 8)))
        self.e_size = ttk.Entry(nf, textvariable=self.v_size, width=7); self.e_size.grid(row=row, column=3, sticky="w")
        self.v_style = tk.StringVar(value=self.s.get("style", "raised"))
        st = ttk.Frame(nf); st.grid(row=row + 1, column=0, columnspan=4, sticky="w")
        ttk.Label(st, text="Text style:").pack(side="left")
        ttk.Radiobutton(st, text="Raised", value="raised", variable=self.v_style).pack(side="left")
        ttk.Radiobutton(st, text="Engraved (inlaid, flush)", value="engraved", variable=self.v_style).pack(side="left")

        cf = ttk.LabelFrame(left, text="Colours", padding=6); cf.grid(row=8, column=0, columnspan=3, sticky="we", pady=4)
        self.v_pc = tk.StringVar(value=self.s["plate_color"]); self.v_tc = tk.StringVar(value=self.s["text_color"])
        self.sw = {}
        for i, (lab, var) in enumerate((("Plate", self.v_pc), ("Text", self.v_tc))):
            ttk.Label(cf, text=lab).grid(row=i, column=0, sticky="e")
            b = tk.Button(cf, width=4, bg=var.get(), relief="groove", command=lambda v=var: self.pick_colour(v)); b.grid(row=i, column=1, padx=4)
            self.sw[str(var)] = b
            ttk.Entry(cf, textvariable=var, width=9).grid(row=i, column=2)
            cb = ttk.Combobox(cf, values=[n for n, _ in sc.COLOUR_PRESETS], width=15, state="readonly"); cb.grid(row=i, column=3, padx=4)
            cb.bind("<<ComboboxSelected>>", lambda e, v=var, c=cb: v.set(dict(sc.COLOUR_PRESETS)[c.get()]))
        ttk.Button(cf, text="Swap", command=self.swap_colours).grid(row=0, column=4, rowspan=2)

        fv = ttk.LabelFrame(left, text="Favourites (font + wording)", padding=6); fv.grid(row=9, column=0, columnspan=3, sticky="we", pady=4)
        self.cb_fav = ttk.Combobox(fv, width=30, state="readonly"); self.cb_fav.grid(row=0, column=0)
        ttk.Button(fv, text="Use", command=self.use_fav, width=5).grid(row=0, column=1)
        ttk.Button(fv, text="Add current", command=self.add_fav).grid(row=0, column=2)
        ttk.Button(fv, text="Remove", command=self.del_fav, width=7).grid(row=0, column=3)
        self._refresh_favs()

        self.v_stl = tk.BooleanVar(value=self.s.get("stl", False))
        ttk.Checkbutton(left, text="Also save separate STLs", variable=self.v_stl).grid(row=10, column=0, sticky="w")
        bt = ttk.Frame(left); bt.grid(row=11, column=0, columnspan=3, sticky="we", pady=6)
        self.b3d = ttk.Button(bt, text="3D preview", command=self.preview3d); self.b3d.pack(side="left", padx=2)
        self.bmk = ttk.Button(bt, text="Make 3MF", command=self.make); self.bmk.pack(side="left", padx=2)
        self.bop = ttk.Button(bt, text="Open folder", command=self.open_folder, state="disabled"); self.bop.pack(side="left", padx=2)

        pf = ttk.LabelFrame(left, text="SolidCraft and save folder", padding=6)
        pf.grid(row=12, column=0, columnspan=3, sticky="we", pady=(4, 0))
        ttk.Label(pf, text="solidcraft-cli").grid(row=0, column=0, sticky="w")
        self.v_cli = tk.StringVar(value=(self.s.get("cli_path") or ""))
        ttk.Entry(pf, textvariable=self.v_cli, width=32).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(pf, text="Browse…", command=self.browse_cli).grid(row=0, column=2)
        ttk.Label(pf, text="Save folder").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.v_out = tk.StringVar(value=sc.output_root(self.s))
        ttk.Entry(pf, textvariable=self.v_out, width=32).grid(row=1, column=1, sticky="we", padx=4, pady=(4, 0))
        ttk.Button(pf, text="Browse…", command=self.browse_output).grid(row=1, column=2, pady=(4, 0))
        self.v_savehint = tk.StringVar()
        ttk.Label(pf, textvariable=self.v_savehint, foreground="#666", wraplength=420, justify="left").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        pf.columnconfigure(1, weight=1)
        self.v_out.trace_add("write", lambda *a: self._update_save_hint())
        self._update_save_hint()
        self._refresh_cli_field()

        ttk.Label(right, text="2D preview (true proportions, real font)").pack(anchor="w")
        self.c2d = tk.Label(right, bg="#ececec"); self.c2d.pack(fill="x")
        self.v_info = tk.StringVar(value="Loading fonts…")
        ttk.Label(right, textvariable=self.v_info, foreground="#1f3a93").pack(anchor="w", pady=(2, 8))
        ttk.Label(right, text="3D preview (rendered by SolidCraft - what will print)").pack(anchor="w")
        self.c3d = tk.Label(right, bg="#dde3ea", text="Press 3D preview", height=20); self.c3d.pack(fill="both", expand=True)
        self.v_status = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.v_status).pack(anchor="w", pady=4)

        for v in [self.v_text, self.v_bold, self.v_auto, self.v_size, self.v_style, self.v_pc, self.v_tc] + list(self.v_num.values()):
            v.trace_add("write", lambda *a: self.schedule())
        self.v_search.trace_add("write", lambda *a: self._fill_list())

    def _insert(self, ch):
        self.e_text.insert(tk.INSERT, ch); self.e_text.focus_set()

    # ---------------- fonts
    def _load_fonts_thread(self):
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
        self.schedule(0)

    def _fallback_font_name(self):
        """Times New Roman when it is installed, otherwise a common face, otherwise the first font."""
        for name in ("Times New Roman", "Liberation Serif", "Liberation Sans", "DejaVu Sans", "Nimbus Roman", "Georgia"):
            if name in self.font_by_name:
                return name
        for want in ("times new roman", "liberation serif", "dejavu sans", "nimbus roman"):
            for name in self.font_by_name:
                if want in name.lower():
                    return name
        return self.fonts[0]["name"]

    def _fill_list(self):
        q = self.v_search.get().lower().strip()
        self.lb.delete(0, "end")
        self._shown = [f["name"] for f in self.fonts if q in f["name"].lower()]
        for n in self._shown:
            self.lb.insert("end", n)
        if self.s["font"] in self._shown:
            i = self._shown.index(self.s["font"]); self.lb.selection_set(i); self.lb.see(i)

    def _on_font_pick(self, e=None):
        sel = self.lb.curselection()
        if sel:
            self.s["font"] = self._shown[sel[0]]; self.v_fontname.set(self.s["font"]); self.schedule()

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
            return f, "  (no bold face for this font - using its normal face)"
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

    def schedule(self, ms=150):
        if self._after:
            self.root.after_cancel(self._after)
        self._after = self.root.after(ms, self.update_preview)

    def update_preview(self):
        self._after = None
        for k, v in (("plate_color", self.v_pc), ("text_color", self.v_tc)):
            try:
                self.sw[str(v)].config(bg=v.get())
            except Exception:
                pass
        self.e_size.config(state="disabled" if self.v_auto.get() else "normal")
        if not self.fonts:
            return
        try:
            p = self.params()
        except Exception as ex:
            self.v_info.set("⚠ " + str(ex)); return
        f, note = self.current_font()
        if not f:
            self.v_info.set("Pick a font"); return
        try:
            w = max(600, self.c2d.winfo_width() or 760)
            img, info = sc.preview_image(p, f, width_px=min(w, 1100))
        except Exception as ex:
            self.v_info.set("⚠ Preview failed: %s" % ex); return
        self._img2d = ImageTk.PhotoImage(img); self.c2d.config(image=self._img2d)
        miss = sc.missing_glyphs(f, p["text"])
        msg = ""
        if info.get("cap_mm"):
            msg = "Text %.1f x %.1f mm, cap height %.2f mm" % (info["text_w"], info["text_h"], info["cap_mm"])
            if not info.get("fits"):
                msg += "  ⚠ text is bigger than the plate inside the margins"
        if miss:
            msg += "  ⚠ font has no glyph for: " + " ".join(miss)
        self.v_info.set(msg + note)
        self.save_settings_soon(p)

    def save_settings_soon(self, p):
        for k in ["text", "length", "height", "thickness", "raise", "margin", "corner", "spacing", "auto_size", "text_size",
                  "bold", "style", "plate_color", "text_color", "stl"]:
            self.s[k] = p[k]
        try:
            sc.save_settings(self.s)
        except Exception:
            pass

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
        f, _ = self.current_font()
        lab = "%s (%s)" % (self.v_text.get(), self.s["font"])
        self.s.setdefault("favourites", []).append({"label": lab, "text": self.v_text.get(), "font": self.s["font"],
                                                     "plate_color": self.v_pc.get(), "text_color": self.v_tc.get()})
        sc.save_settings(self.s); self._refresh_favs(); self.cb_fav.set(lab)

    def del_fav(self):
        i = self.cb_fav.current()
        if i >= 0:
            del self.s["favourites"][i]; sc.save_settings(self.s); self._refresh_favs(); self.cb_fav.set("")

    # ---------------- builds
    def _start(self, kind):
        if self.busy:
            return
        self._sync_paths()
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
        self.b3d.config(state="disabled"); self.bmk.config(state="disabled")
        threading.Thread(target=self._worker, args=(kind, p, f), daemon=True).start()

    def preview3d(self):
        self._start("preview")

    def make(self):
        self._start("make")

    def _worker(self, kind, p, f):
        log = lambda m: self.q.put(("status", m))
        try:
            res = sc.build_sign(p, f, log=log)
            out = sc.save_outputs(res, p, root=sc.output_root(self.s), log=log) if kind == "make" else None
            self.q.put(("done", (kind, res, out)))
        except Exception as ex:
            self.q.put(("fail", str(ex)))

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "fonts":
                    self._set_fonts(data)
                elif kind == "status":
                    self.v_status.set(data)
                elif kind == "error":
                    self.v_info.set("Font list failed: " + data[-300:])
                elif kind == "fail":
                    self.busy = False; self.b3d.config(state="normal"); self.bmk.config(state="normal")
                    self.v_status.set("Failed"); messagebox.showerror("Sign Maker", data[-1500:])
                elif kind == "done":
                    self.busy = False; self.b3d.config(state="normal"); self.bmk.config(state="normal")
                    k, res, out = data
                    if res.get("snapshot"):
                        im = Image.open(res["snapshot"]); w = max(400, self.c3d.winfo_width()); h = max(250, self.c3d.winfo_height())
                        im.thumbnail((w, h)); self._img3d = ImageTk.PhotoImage(im); self.c3d.config(image=self._img3d, text="")
                    tb = res["text_bbox"]
                    msg = "Plate %.1f x %.1f x %.2f mm; text %.2f x %.2f mm, top at %.2f mm, cap height %.2f mm" % (
                        float(self.v_num["length"].get()), float(self.v_num["height"].get()), float(self.v_num["thickness"].get()),
                        tb["max"][0] - tb["min"][0], tb["max"][1] - tb["min"][1], tb["max"][2], res["cap"])
                    if out:
                        self.last_folder = out["folder"]; self.bop.config(state="normal")
                        msg = "Saved %s.3mf in %s.  " % (out["base"], out["folder"]) + msg
                    self.v_status.set(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def open_folder(self):
        if self.last_folder and os.path.isdir(self.last_folder):
            if hasattr(os, "startfile"):
                os.startfile(self.last_folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.last_folder])
            else:
                subprocess.Popen(["xdg-open", self.last_folder])

    def _update_save_hint(self):
        sep = "\\" if os.name == "nt" else "/"
        root = (self.v_out.get() or "").strip() or sc.default_output_dir()
        self.v_savehint.set("Each sign is saved in " + root + sep + "<wording>")

    def _refresh_cli_field(self):
        try:
            self.v_cli.set(sc.find_cli(self.s))
        except FileNotFoundError:
            self.v_cli.set((self.s.get("cli_path") or "").strip())

    def _sync_paths(self):
        """Remember the CLI and the save folder in the settings file."""
        out = self.v_out.get().strip()
        self.s["output_dir"] = out if out and os.path.normcase(out) != os.path.normcase(sc.default_output_dir()) else ""
        cli = self.v_cli.get().strip()
        self.s["cli_path"] = cli
        try:
            sc.save_settings(self.s)
        except Exception:
            pass

    def browse_cli(self):
        if os.name == "nt":
            types = [("solidcraft-cli", "solidcraft-cli.exe"), ("All files", "*.*")]
        else:
            types = [("All files", "*")]
        p = filedialog.askopenfilename(title="Locate solidcraft-cli", filetypes=types)
        if not p:
            return False
        p = os.path.normpath(p)
        if not os.path.isfile(p):
            messagebox.showerror("Sign Maker", "That file does not exist.")
            return False
        self.v_cli.set(p)
        self._sync_paths()
        self.v_status.set("Using SolidCraft: " + p)
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
        try:
            path = sc.find_cli(self.s)
        except FileNotFoundError:
            path = None
        if path:
            self.v_status.set("SolidCraft: " + path)
            return
        cli_name = "solidcraft-cli.exe" if os.name == "nt" else "solidcraft-cli"
        self.v_status.set("SolidCraft CLI not found yet. 2D preview works; Browse to " + cli_name + " for 3D and 3MF.")
        if self.s.get("cli_prompted"):
            return
        self.s["cli_prompted"] = True
        try:
            sc.save_settings(self.s)
        except Exception:
            pass
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

    def on_close(self):
        try:
            self.update_preview_settings_only()
        except Exception:
            pass
        self.root.destroy()

    def update_preview_settings_only(self):
        self.save_settings_soon(self.params())


def selftest():
    log = []
    os.makedirs(sc.DATA_DIR, exist_ok=True)
    root = tk.Tk(); root.withdraw()
    app = App(root, selftest=True)
    log.append("fonts: %d" % len(app.fonts))
    for name in ("Bunchló Trom GC (bold)", "Times New Roman"):
        f = app.font_by_name.get(name)
        log.append("%s -> %s" % (name, f["path"] if f else "MISSING"))
        if f:
            p = sc.load_settings(); p["text"] = "Telefón ⁊" if "Bun" in name else "TELEPHONE"
            img, info = sc.preview_image(p, f)
            img.save(os.path.join(sc.DATA_DIR, "selftest_%s.png" % ("bunchlo" if "Bun" in name else "times")))
            log.append("  preview ok %s cap %.2f fits %s" % (img.size, info["cap_mm"], info["fits"]))
    if app.fonts and not any(line.startswith("  preview ok") for line in log):
        f = app.font_by_name.get(app.s.get("font")) or app.fonts[0]
        p = sc.load_settings(); p["text"] = "Telefón"
        img, info = sc.preview_image(p, f)
        img.save(os.path.join(sc.DATA_DIR, "selftest_fallback.png"))
        log.append("fallback %s preview ok %s cap %.2f fits %s" % (f["name"], img.size, info.get("cap_mm") or 0, info.get("fits")))
    root.update(); app.update_preview(); log.append("info: " + app.v_info.get())
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
    if "--selftest" in sys.argv:
        try:
            selftest()
        except Exception:
            os.makedirs(sc.DATA_DIR, exist_ok=True)
            open(os.path.join(sc.DATA_DIR, "selftest.log"), "w", encoding="utf-8").write(traceback.format_exc())
            raise
        sys.exit(0)
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.3)
    except Exception:
        pass
    App(root)
    root.mainloop()
