#!/usr/bin/env python3
"""
YouTube -> MP3 Converter
 
Single-window, menu-driven layout:
    File menu        - choose/open download folder, exit
    Preferences menu - MP3 bitrate / sample rate
    Sign In menu     - AcoustID API key + matching toggle
    Options menu     - misc app behavior
 
Left panel:
    - Paste a YouTube link -> metadata is fetched automatically
    - Edit Title / Artist / Album / Year / Track / Genre
    - "Add Song to Queue" downloads it immediately (no separate
      Start button -- queuing IS starting)
    - Directory field controls where songs are saved
    - A small queue list shows Waiting / Downloading / Complete /
      Error songs (color-coded), capped at 25 pending at a time
 
Right panel:
    - Shows every MP3 already in the download folder
    - Click a row to load its tags into the left panel and edit them
      ("Add Song to Queue" becomes "Save Tags" while a row is selected)
 
Requirements:
    pip install yt-dlp mutagen pyacoustid
 
Also required:
    ffmpeg
 
Optional:
    fpcalc / Chromaprint
    AcoustID API key
"""
 
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import webbrowser
 
try:
    import yt_dlp
except ImportError:
    yt_dlp = None
 
try:
    from mutagen.id3 import (
        ID3,
        APIC,
        TIT2,
        TPE1,
        TALB,
        TDRC,
        TCON,
        TRCK,
        error as ID3Error,
    )
except ImportError:
    ID3 = None
 
try:
    from mutagen.mp3 import MP3 as MP3Info
except ImportError:
    MP3Info = None
 
try:
    import acoustid
except ImportError:
    acoustid = None
 
 
# ============================================================
# CONFIG
# ============================================================
 
CONFIG_PATH = os.path.join(
    os.path.expanduser("~"),
    ".yt_mp3_tagger_config.json"
)
 
DEFAULT_OUTPUT = os.path.join(
    os.path.expanduser("~"),
    "Downloads"
)
 
DEFAULTS = {
    "acoustid_api_key": "",
    "output_dir": DEFAULT_OUTPUT,
    "quality": "320",
    "sample_rate": "48000",
    "skip_existing": False,
    "auto_thumbnail": True,
    "confirm_remove": False,
    "auto_identify": True,
}
 
MAX_PENDING_QUEUE = 25
 
PALETTE = {
    "bg": "#1b1c1f",
    "panel": "#212226",
    "field_bg": "#2a2b30",
    "field_border": "#3a3b40",
    "border": "#333438",
    "text": "#e7e7e8",
    "muted": "#9a9a9e",
    "accent": "#3b6fd8",
    "accent_hover": "#2f5bb8",
    "success_bg": "#123a1f",
    "success_fg": "#7be3a0",
    "warn_bg": "#4a3f12",
    "warn_fg": "#ffd66b",
    "error_bg": "#3a1414",
    "error_fg": "#ff8f8f",
    "danger": "#ff6b6b",
}
 
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
 
 
# ============================================================
# CONFIG FUNCTIONS
# ============================================================
 
def load_saved_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
 
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged
 
 
def save_setting(key, value):
    data = load_saved_config()
    data[key] = value
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
 
 
def clear_saved_api_key():
    save_setting("acoustid_api_key", "")
 
 
# ============================================================
# HELPERS
# ============================================================
 
def safe_filename(name):
    if not name:
        name = "Unknown"
 
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" .")
 
    if len(name) > 180:
        name = name[:180].rstrip()
 
    return name or "Unknown"
 
 
def find_ffmpeg():
    return shutil.which("ffmpeg")
 
 
def find_fpcalc():
    return shutil.which("fpcalc")
 
 
def open_folder_in_explorer(path):
    if not path or not os.path.isdir(path):
        return
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
 
 
# ============================================================
# THEME
# ============================================================
 
def apply_dark_theme(root):
    root.configure(bg=PALETTE["bg"])
 
    style = ttk.Style(root)
 
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
 
    style.configure("TFrame", background=PALETTE["bg"])
    style.configure("Panel.TFrame", background=PALETTE["panel"])
 
    style.configure(
        "TLabel",
        background=PALETTE["bg"],
        foreground=PALETTE["text"],
        font=FONT
    )
 
    style.configure(
        "Panel.TLabel",
        background=PALETTE["panel"],
        foreground=PALETTE["text"],
        font=FONT_SMALL
    )
 
    style.configure(
        "Muted.TLabel",
        background=PALETTE["panel"],
        foreground=PALETTE["muted"],
        font=FONT_SMALL
    )
 
    style.configure(
        "BgMuted.TLabel",
        background=PALETTE["bg"],
        foreground=PALETTE["muted"],
        font=FONT_SMALL
    )
 
    style.configure(
        "TEntry",
        fieldbackground=PALETTE["field_bg"],
        foreground=PALETTE["text"],
        insertcolor=PALETTE["text"],
        bordercolor=PALETTE["field_border"],
        lightcolor=PALETTE["field_border"],
        darkcolor=PALETTE["field_border"],
        padding=5
    )
 
    style.configure(
        "TButton",
        font=FONT_SMALL,
        padding=6,
        relief="flat",
        background=PALETTE["panel"],
        foreground=PALETTE["text"]
    )
    style.map("TButton", background=[("active", "#2c2d32")])
 
    style.configure(
        "Accent.TButton",
        font=FONT_BOLD,
        padding=9,
        relief="flat",
        background=PALETTE["accent"],
        foreground="#ffffff"
    )
    style.map(
        "Accent.TButton",
        background=[("active", PALETTE["accent_hover"]), ("disabled", "#43444a")],
        foreground=[("disabled", "#9a9a9e")]
    )
 
    style.configure(
        "Danger.TButton",
        font=FONT_SMALL,
        padding=6,
        relief="flat",
        background=PALETTE["panel"],
        foreground=PALETTE["danger"]
    )
 
    style.configure(
        "Treeview",
        background=PALETTE["bg"],
        fieldbackground=PALETTE["bg"],
        foreground=PALETTE["text"],
        rowheight=26,
        font=FONT_SMALL,
        bordercolor=PALETTE["border"]
    )
    style.map("Treeview", background=[("selected", "#33465e")], foreground=[("selected", "#ffffff")])
 
    style.configure(
        "Treeview.Heading",
        background=PALETTE["panel"],
        foreground=PALETTE["text"],
        font=FONT_BOLD,
        relief="flat"
    )
    style.map("Treeview.Heading", background=[("active", "#2c2d32")])
 
 
# ============================================================
# APP
# ============================================================
 
class YTMp3ConverterApp:
 
    def __init__(self, root):
        self.root = root
 
        root.title("Youtube to mp3 converter")
        root.geometry("1200x820")
        root.minsize(900, 600)
 
        apply_dark_theme(root)
 
        # --------------------------------------------
        # STATE
        # --------------------------------------------
 
        cfg = load_saved_config()
 
        self.output_dir = cfg["output_dir"]
 
        self.apikey_var = tk.StringVar(value=cfg["acoustid_api_key"])
        self.quality_var = tk.StringVar(value=cfg["quality"])
        self.sample_rate_var = tk.StringVar(value=cfg["sample_rate"])
 
        self.skip_existing_var = tk.BooleanVar(value=cfg["skip_existing"])
        self.auto_thumbnail_var = tk.BooleanVar(value=cfg["auto_thumbnail"])
        self.confirm_remove_var = tk.BooleanVar(value=cfg["confirm_remove"])
        self.autoid_var = tk.BooleanVar(value=cfg["auto_identify"])
 
        self.queue = []              # list of item dicts, each with a unique "id"
        self.downloading = False
        self.current_item_id = None
 
        self._prefetch_seen_url = ""
        self.current_thumbnail = None
 
        self.context_widget = None
        self.selected_import_path = None
        self._import_files = []
        self._sort_reverse = {}
 
        # --------------------------------------------
        # MENU BAR
        # --------------------------------------------
 
        self._build_menu_bar()
 
        # --------------------------------------------
        # RIGHT CLICK MENU (cut / copy / paste / select all)
        # --------------------------------------------
 
        self.context_menu = tk.Menu(root, tearoff=0)
        self.context_menu.add_command(label="Cut", command=self.context_cut)
        self.context_menu.add_command(label="Copy", command=self.context_copy)
        self.context_menu.add_command(label="Paste", command=self.context_paste)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Select All", command=self.context_select_all)
 
        # --------------------------------------------
        # MAIN LAYOUT
        # --------------------------------------------
 
        self.build_ui()
 
        if yt_dlp is None or ID3 is None:
            self.status_var.set(
                "Missing dependencies. Run: pip install yt-dlp mutagen pyacoustid"
            )
 
        self._maximize_window()
        root.bind("<F11>", lambda e: self._maximize_window())
 
        self._refresh_grid()
 
    # ========================================================
    # WINDOW STATE
    # ========================================================
 
    def _maximize_window(self):
        try:
            self.root.state("zoomed")
            return
        except tk.TclError:
            pass
 
        try:
            self.root.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass
 
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
        except Exception:
            pass
 
    # ========================================================
    # MENU BAR
    # ========================================================
 
    def _build_menu_bar(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
 
        # ---- File ----
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Choose Download Folder...", command=self.choose_output)
        file_menu.add_command(label="Open Download Folder", command=self.open_output_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)
 
        # ---- Preferences ----
        prefs_menu = tk.Menu(menubar, tearoff=0)
 
        bitrate_menu = tk.Menu(prefs_menu, tearoff=0)
        for value in ("128", "192", "256", "320"):
            bitrate_menu.add_radiobutton(
                label=f"{value} kbps",
                variable=self.quality_var,
                value=value,
                command=lambda v=value: save_setting("quality", v)
            )
        prefs_menu.add_cascade(label="MP3 Bitrate", menu=bitrate_menu)
 
        rate_menu = tk.Menu(prefs_menu, tearoff=0)
        for value in ("44100", "48000"):
            rate_menu.add_radiobutton(
                label=f"{value} Hz",
                variable=self.sample_rate_var,
                value=value,
                command=lambda v=value: save_setting("sample_rate", v)
            )
        prefs_menu.add_cascade(label="Sample Rate", menu=rate_menu)
 
        menubar.add_cascade(label="Preferences", menu=prefs_menu)
 
        # ---- Sign In ----
        self.signin_menu = tk.Menu(menubar, tearoff=0)
        self._rebuild_signin_menu()
        menubar.add_cascade(label="Sign In", menu=self.signin_menu)
 
        # ---- Options ----
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_checkbutton(
            label="Skip Songs That Already Exist",
            variable=self.skip_existing_var,
            command=lambda: save_setting("skip_existing", self.skip_existing_var.get())
        )
        options_menu.add_checkbutton(
            label="Embed YouTube Thumbnail as Cover Art",
            variable=self.auto_thumbnail_var,
            command=lambda: save_setting("auto_thumbnail", self.auto_thumbnail_var.get())
        )
        options_menu.add_checkbutton(
            label="Confirm Before Removing a Queued Song",
            variable=self.confirm_remove_var,
            command=lambda: save_setting("confirm_remove", self.confirm_remove_var.get())
        )
        options_menu.add_separator()
        options_menu.add_command(label="Check FFmpeg Installation", command=self._check_ffmpeg)
        options_menu.add_command(label="Open Settings Folder", command=self._open_settings_folder)
        options_menu.add_separator()
        options_menu.add_command(label="Reset All Saved Settings...", command=self._reset_settings)
        menubar.add_cascade(label="Options", menu=options_menu)
 
    def _rebuild_signin_menu(self):
        self.signin_menu.delete(0, "end")
 
        if self.apikey_var.get().strip():
            self.signin_menu.add_command(label="Signed In", state="disabled")
            self.signin_menu.add_command(label="Sign Out", command=self.sign_out)
        else:
            self.signin_menu.add_command(label="Sign In...", command=self.sign_in_flow)
 
        self.signin_menu.add_separator()
        self.signin_menu.add_checkbutton(
            label="Use AcoustID/MusicBrainz Matching",
            variable=self.autoid_var,
            command=lambda: save_setting("auto_identify", self.autoid_var.get())
        )
        self.signin_menu.add_separator()
        self.signin_menu.add_command(label="Get a Free AcoustID API Key...", command=self.open_api_key_site)
 
        fpcalc_status = "fpcalc found" if find_fpcalc() else "fpcalc not found on PATH"
        self.signin_menu.add_command(label=fpcalc_status, state="disabled")
 
    def sign_in_flow(self):
        key = simpledialog.askstring("Sign In", "Paste your AcoustID API key:", parent=self.root)
        if key and key.strip():
            save_setting("acoustid_api_key", key.strip())
            self.apikey_var.set(key.strip())
            self._rebuild_signin_menu()
 
    def sign_out(self):
        clear_saved_api_key()
        self.apikey_var.set("")
        self._rebuild_signin_menu()
 
    def open_api_key_site(self):
        webbrowser.open("https://acoustid.org/api-key")
 
    def _check_ffmpeg(self):
        path = find_ffmpeg()
        if path:
            messagebox.showinfo("FFmpeg found", f"FFmpeg is installed at:\n{path}")
        else:
            messagebox.showwarning(
                "FFmpeg not found",
                "FFmpeg was not found on your PATH. Downloads will fail without it."
            )
 
    def _open_settings_folder(self):
        open_folder_in_explorer(os.path.dirname(CONFIG_PATH) or os.path.expanduser("~"))
 
    def _reset_settings(self):
        if not messagebox.askyesno(
            "Reset settings",
            "This erases your saved API key, output folder, and all preferences. Continue?"
        ):
            return
 
        try:
            if os.path.exists(CONFIG_PATH):
                os.remove(CONFIG_PATH)
        except OSError:
            pass
 
        self.output_dir = DEFAULTS["output_dir"]
        self.output_dir_var.set(self.output_dir)
 
        self.quality_var.set(DEFAULTS["quality"])
        self.sample_rate_var.set(DEFAULTS["sample_rate"])
 
        self.skip_existing_var.set(DEFAULTS["skip_existing"])
        self.auto_thumbnail_var.set(DEFAULTS["auto_thumbnail"])
        self.confirm_remove_var.set(DEFAULTS["confirm_remove"])
        self.autoid_var.set(DEFAULTS["auto_identify"])
 
        self.apikey_var.set("")
        self._rebuild_signin_menu()
 
        self._refresh_grid()
        self.status_var.set("Settings reset to defaults.")
 
    # ========================================================
    # RIGHT CLICK COPY / PASTE
    # ========================================================
 
    def _bind_context_menu(self, entry):
        entry.bind("<Button-3>", self.show_context_menu)
        entry.bind("<Control-Button-1>", self.show_context_menu)
 
    def show_context_menu(self, event):
        widget = event.widget
        if isinstance(widget, (tk.Entry, ttk.Entry)):
            self.context_widget = widget
            try:
                widget.focus_set()
                self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()
 
    def context_cut(self):
        try:
            self.context_widget.event_generate("<<Cut>>")
        except Exception:
            pass
 
    def context_copy(self):
        try:
            self.context_widget.event_generate("<<Copy>>")
        except Exception:
            pass
 
    def context_paste(self):
        try:
            self.context_widget.event_generate("<<Paste>>")
        except Exception:
            pass
 
    def context_select_all(self):
        try:
            self.context_widget.select_range(0, tk.END)
            self.context_widget.icursor(tk.END)
        except Exception:
            pass
 
    # ========================================================
    # SCROLLABLE FRAME HELPER (for the left panel)
    # ========================================================
 
    def _make_scrollable_frame(self, parent, bg):
        canvas = tk.Canvas(parent, bg=bg, highlightthickness=0)
        vbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=bg)
 
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window, width=e.width))
 
        def _wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
 
        def _on_enter(_e):
            canvas.bind_all("<MouseWheel>", _wheel)
            canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
 
        def _on_leave(_e):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
 
        canvas.bind("<Enter>", _on_enter)
        canvas.bind("<Leave>", _on_leave)
 
        canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")
 
        return inner
 
    # ========================================================
    # FIELD HELPERS
    # ========================================================
 
    def _add_field(self, parent, label, var):
        ttk.Label(parent, text=label, style="Panel.TLabel").pack(anchor="w", padx=14, pady=(10, 2))
        entry = ttk.Entry(parent, textvariable=var, font=FONT)
        entry.pack(fill="x", padx=14, ipady=3)
        self._bind_context_menu(entry)
        return entry
 
    def _add_field_row(self, parent, fields):
        row = tk.Frame(parent, bg=PALETTE["panel"])
        row.pack(fill="x", padx=14, pady=(10, 2))
        for i, (label, var) in enumerate(fields):
            col = tk.Frame(row, bg=PALETTE["panel"])
            col.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 8, 0))
            ttk.Label(col, text=label, style="Panel.TLabel").pack(anchor="w")
            entry = ttk.Entry(col, textvariable=var, font=FONT)
            entry.pack(fill="x", ipady=3)
            self._bind_context_menu(entry)
 
    # ========================================================
    # MAIN UI
    # ========================================================
 
    def build_ui(self):
        main = tk.Frame(self.root, bg=PALETTE["bg"])
        main.pack(fill="both", expand=True)
 
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
 
        # ---------------- LEFT PANEL ----------------
 
        left_outer = tk.Frame(main, bg=PALETTE["panel"], width=340)
        left_outer.grid(row=0, column=0, sticky="nsw")
        left_outer.grid_propagate(False)
 
        left = left_outer
 
        ttk.Label(left, text="YouTube Link", style="Panel.TLabel").pack(anchor="w", padx=14, pady=(14, 2))
 
        url_row = tk.Frame(left, bg=PALETTE["panel"])
        url_row.pack(fill="x", padx=14)
 
        self.url_entry = ttk.Entry(url_row, font=FONT)
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self._bind_context_menu(self.url_entry)
        self.url_entry.bind("<Return>", lambda e: self.start_metadata_prefetch())
        self.url_entry.bind("<FocusOut>", lambda e: self.start_metadata_prefetch())
        self.url_entry.bind("<FocusIn>", self._on_url_focus_in)
 
        ttk.Button(url_row, text="Paste", command=self.paste_url).pack(side="left", padx=(6, 0))
 
        self.field_title = tk.StringVar()
        self.field_artist = tk.StringVar()
        self.field_album = tk.StringVar()
        self.field_year = tk.StringVar()
        self.field_track = tk.StringVar()
        self.field_genre = tk.StringVar()
 
        self._add_field(left, "Title", self.field_title)
        self._add_field(left, "Artist", self.field_artist)
        self._add_field(left, "Album", self.field_album)
        self._add_field_row(left, [
            ("Year", self.field_year),
            ("Track", self.field_track),
            ("Genre", self.field_genre),
        ])
 
        self.left_action_button = ttk.Button(
            left,
            text="Add Song to Queue",
            style="Accent.TButton",
            command=self.add_to_queue
        )
        self.left_action_button.pack(fill="x", padx=14, pady=(16, 10), ipady=4)
 
        ttk.Label(left, text="Directory", style="Panel.TLabel").pack(anchor="w", padx=14, pady=(4, 2))
 
        dir_row = tk.Frame(left, bg=PALETTE["panel"])
        dir_row.pack(fill="x", padx=14)
 
        self.output_dir_var = tk.StringVar(value=self.output_dir)
        dir_entry = ttk.Entry(dir_row, textvariable=self.output_dir_var, font=FONT)
        dir_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self._bind_context_menu(dir_entry)
        dir_entry.bind("<Return>", lambda e: self._apply_typed_directory())
 
        ttk.Button(dir_row, text="...", width=3, command=self.choose_output).pack(side="left", padx=(6, 0))
 
        ttk.Label(
            left,
            text="Songs are downloaded to and browsed from this folder.",
            style="Muted.TLabel",
            wraplength=300
        ).pack(anchor="w", padx=14, pady=(4, 12))
 
        # ---- QUEUE ----
 
        ttk.Label(left, text=f"Queue (up to {MAX_PENDING_QUEUE} at a time)", style="Panel.TLabel").pack(
            anchor="w", padx=14, pady=(6, 4)
        )
 
        queue_frame = tk.Frame(left, bg=PALETTE["panel"])
        queue_frame.pack(fill="x", padx=14)
 
        self.queue_tree = ttk.Treeview(
            queue_frame,
            columns=("title", "artist", "status"),
            show="headings",
            selectmode="browse",
            height=9
        )
        self.queue_tree.heading("title", text="Title")
        self.queue_tree.heading("artist", text="Artist")
        self.queue_tree.heading("status", text="Status")
        self.queue_tree.column("title", width=115, anchor="w")
        self.queue_tree.column("artist", width=90, anchor="w")
        self.queue_tree.column("status", width=90, anchor="w")
 
        queue_scroll = ttk.Scrollbar(queue_frame, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=queue_scroll.set)
 
        self.queue_tree.pack(side="left", fill="both", expand=True)
        queue_scroll.pack(side="right", fill="y")
 
        self.queue_tree.tag_configure("waiting", foreground=PALETTE["muted"])
        self.queue_tree.tag_configure("downloading", background=PALETTE["warn_bg"], foreground=PALETTE["warn_fg"])
        self.queue_tree.tag_configure("converting", background=PALETTE["warn_bg"], foreground=PALETTE["warn_fg"])
        self.queue_tree.tag_configure("complete", background=PALETTE["success_bg"], foreground=PALETTE["success_fg"])
        self.queue_tree.tag_configure("skipped", foreground=PALETTE["muted"])
        self.queue_tree.tag_configure("error", background=PALETTE["error_bg"], foreground=PALETTE["error_fg"])
 
        self.queue_tree.bind("<Delete>", lambda e: self._remove_selected_queue_item())
 
        def _queue_wheel(e):
            self.queue_tree.yview_scroll(int(-1 * (e.delta / 120)), "units")
            return "break"
 
        self.queue_tree.bind("<MouseWheel>", _queue_wheel)
 
        queue_buttons = tk.Frame(left, bg=PALETTE["panel"])
        queue_buttons.pack(fill="x", padx=14, pady=(6, 16))
 
        ttk.Button(queue_buttons, text="Remove Selected", style="Danger.TButton",
                   command=self._remove_selected_queue_item).pack(side="left")
        ttk.Button(queue_buttons, text="Clear Completed",
                   command=self._clear_completed_queue).pack(side="left", padx=(6, 0))
 
        # ---------------- RIGHT PANEL (grid) ----------------
 
        right_outer = tk.Frame(main, bg=PALETTE["bg"])
        right_outer.grid(row=0, column=1, sticky="nsew")
        right_outer.rowconfigure(0, weight=1)
        right_outer.columnconfigure(0, weight=1)
 
        grid_frame = tk.Frame(right_outer, bg=PALETTE["bg"])
        grid_frame.grid(row=0, column=0, sticky="nsew", padx=(1, 0))
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.columnconfigure(0, weight=1)
 
        columns = ("filename", "path", "tag", "title", "artist", "album", "track")
        self.grid_tree = ttk.Treeview(grid_frame, columns=columns, show="headings", selectmode="browse")
 
        headings = {
            "filename": "Filename", "path": "Path", "tag": "Tag", "title": "Title",
            "artist": "Artist", "album": "Album", "track": "Track"
        }
        widths = {
            "filename": 240, "path": 170, "tag": 160, "title": 200,
            "artist": 160, "album": 160, "track": 70
        }
 
        for col in columns:
            self.grid_tree.heading(col, text=headings[col], command=lambda c=col: self._sort_grid(c))
            self.grid_tree.column(col, width=widths[col], anchor="w")
 
        v_scroll = ttk.Scrollbar(grid_frame, orient="vertical", command=self.grid_tree.yview)
        h_scroll = ttk.Scrollbar(grid_frame, orient="horizontal", command=self.grid_tree.xview)
        self.grid_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
 
        self.grid_tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
 
        self.grid_tree.bind("<<TreeviewSelect>>", self._on_grid_select)
 
        # ---------------- FILTER BAR ----------------
 
        filter_bar = tk.Frame(main, bg=PALETTE["panel"])
        filter_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
 
        ttk.Label(filter_bar, text="Filter:", style="Panel.TLabel").pack(side="left", padx=(14, 8), pady=8)
 
        self.filter_var = tk.StringVar()
        filter_entry = ttk.Entry(filter_bar, textvariable=self.filter_var, font=FONT)
        filter_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=8)
        self._bind_context_menu(filter_entry)
        self.filter_var.trace_add("write", lambda *a: self._redraw_grid())
 
        ttk.Button(filter_bar, text="Clear", command=lambda: self.filter_var.set("")).pack(
            side="left", padx=(0, 14), pady=8
        )
 
        # ---------------- STATUS BAR ----------------
 
        status_bar = tk.Frame(main, bg=PALETTE["bg"])
        status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
 
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(status_bar, textvariable=self.status_var, style="BgMuted.TLabel").pack(
            side="left", padx=14, pady=6
        )
 
        self.stats_var = tk.StringVar(value="")
        ttk.Label(status_bar, textvariable=self.stats_var, style="BgMuted.TLabel").pack(
            side="right", padx=14, pady=6
        )
 
    # ========================================================
    # URL / METADATA PREFETCH
    # ========================================================
 
    def _on_url_focus_in(self, _e=None):
        if self.selected_import_path is not None:
            self.selected_import_path = None
            if self.grid_tree.selection():
                self.grid_tree.selection_remove(self.grid_tree.selection())
            self._clear_metadata_fields()
            self._refresh_left_action_button()
 
    def paste_url(self):
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            return
 
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, text)
 
        self.start_metadata_prefetch()
 
    def start_metadata_prefetch(self):
        url = self.url_entry.get().strip()
 
        if not url or url == self._prefetch_seen_url or yt_dlp is None:
            return
 
        self._prefetch_seen_url = url
        self.status_var.set("Reading video information...")
 
        threading.Thread(target=self._prefetch_metadata, args=(url,), daemon=True).start()
 
    def _prefetch_metadata(self, url):
        try:
            opts = {"quiet": True, "skip_download": True, "noplaylist": True}
 
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
 
            guess = self._guess_metadata_from_title(info.get("title"), info.get("uploader"))
 
            metadata = {
                "url": url,
                "thumbnail": info.get("thumbnail"),
                "artist": guess.get("artist") or "",
                "title": guess.get("title") or "",
                "album": info.get("album") or "",
                "year": str(info.get("release_year")) if info.get("release_year") else "",
            }
 
            if not metadata["artist"]:
                metadata["artist"] = info.get("artist") or info.get("creator") or info.get("uploader") or ""
 
            self.root.after(0, lambda m=metadata: self._apply_prefetch_metadata(m))
 
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Could not read metadata: {e}"))
 
    def _apply_prefetch_metadata(self, metadata):
        self.field_artist.set(metadata["artist"])
        self.field_title.set(metadata["title"])
        self.field_album.set(metadata["album"])
        self.field_year.set(metadata["year"])
 
        self.current_thumbnail = metadata.get("thumbnail")
        self.status_var.set("Metadata loaded. Check it, then click Add Song to Queue.")
 
    @staticmethod
    def _guess_metadata_from_title(video_title, uploader):
        if not video_title:
            return {}
 
        title = video_title.strip()
 
        junk_pattern = re.compile(
            r"[\(\[]\s*"
            r"(official\s*)?"
            r"(music\s*)?"
            r"(video|audio|lyrics?|visualizer|"
            r"lyric\s*video|hd|4k|remastered|"
            r"explicit|clean)"
            r"\s*[\)\]]",
            re.IGNORECASE
        )
 
        title = junk_pattern.sub("", title)
        title = re.sub(r"\s{2,}", " ", title).strip(" -\u2013\u2014|")
 
        for sep in (" - ", " \u2013 ", " \u2014 ", " | "):
            if sep in title:
                left, right = title.split(sep, 1)
                left = left.strip()
                right = right.strip()
                if left and right:
                    return {"artist": left, "title": right}
 
        guessed_artist = None
        if uploader:
            guessed_artist = re.sub(
                r"\s*(-\s*topic|vevo|official)\s*$", "", uploader, flags=re.IGNORECASE
            ).strip()
 
        return {"artist": guessed_artist, "title": title or None}
 
    # ========================================================
    # DIRECTORY
    # ========================================================
 
    def choose_output(self):
        folder = filedialog.askdirectory(title="Choose download folder", initialdir=self.output_dir)
        if folder:
            self.output_dir = folder
            self.output_dir_var.set(folder)
            save_setting("output_dir", folder)
            self._refresh_grid()
 
    def _apply_typed_directory(self):
        folder = self.output_dir_var.get().strip()
        if folder and os.path.isdir(folder):
            self.output_dir = folder
            save_setting("output_dir", folder)
            self._refresh_grid()
        else:
            self.status_var.set("That folder doesn't exist.")
 
    def open_output_folder(self):
        if not os.path.isdir(self.output_dir):
            messagebox.showinfo("Folder not found", "That download folder doesn't exist yet.")
            return
        open_folder_in_explorer(self.output_dir)
 
    # ========================================================
    # FIELD CLEARING
    # ========================================================
 
    def _clear_metadata_fields(self):
        self.field_title.set("")
        self.field_artist.set("")
        self.field_album.set("")
        self.field_year.set("")
        self.field_track.set("")
        self.field_genre.set("")
        self.current_thumbnail = None
 
    def _clear_new_song_form(self):
        self.url_entry.delete(0, tk.END)
        self._prefetch_seen_url = ""
        self._clear_metadata_fields()
 
    # ========================================================
    # ADD TO QUEUE (starts downloading immediately)
    # ========================================================
 
    def add_to_queue(self):
        url = self.url_entry.get().strip()
 
        if not url:
            messagebox.showerror("Missing URL", "Paste a YouTube URL first.")
            return
 
        title = self.field_title.get().strip()
        if not title:
            messagebox.showerror("Missing title", "Make sure the Song Title field is filled in.")
            return
 
        pending = sum(1 for it in self.queue if it["status"] in ("Waiting", "Downloading", "Converting"))
        if pending >= MAX_PENDING_QUEUE:
            messagebox.showinfo(
                "Queue full",
                f"You can queue up to {MAX_PENDING_QUEUE} songs at a time. "
                "Wait for some to finish, or clear completed ones, before adding more."
            )
            return
 
        item = {
            "id": uuid.uuid4().hex,
            "url": url,
            "artist": self.field_artist.get().strip(),
            "title": title,
            "album": self.field_album.get().strip(),
            "year": self.field_year.get().strip(),
            "track": self.field_track.get().strip(),
            "genre": self.field_genre.get().strip(),
            "thumbnail": self.current_thumbnail,
            "status": "Waiting",
            "progress": 0,
            "error": "",
        }
 
        self.queue.append(item)
        self.queue_tree.insert("", "end", iid=item["id"], values=("", "", ""))
        self._update_queue_row(item["id"])
 
        self._clear_new_song_form()
        self.status_var.set(f"Queued '{item['title']}'. Downloading...")
 
        self._maybe_start_processing()
 
    def _find_item(self, item_id):
        for item in self.queue:
            if item["id"] == item_id:
                return item
        return None
 
    # ========================================================
    # QUEUE LIST UI
    # ========================================================
 
    def _update_queue_row(self, item_id):
        item = self._find_item(item_id)
        if item is None or not self.queue_tree.exists(item_id):
            return
 
        status = item["status"]
        if status == "Downloading":
            status_text = f"Downloading {int(item.get('progress', 0))}%"
        else:
            status_text = status
 
        self.queue_tree.item(
            item_id,
            values=(item["title"], item["artist"], status_text),
            tags=(status.lower(),)
        )
 
    def _remove_selected_queue_item(self):
        selected = self.queue_tree.selection()
        if not selected:
            return
        self.remove_queue_item(selected[0])
 
    def remove_queue_item(self, item_id):
        if item_id == self.current_item_id:
            messagebox.showinfo("In progress", "This song is currently downloading and can't be removed.")
            return
 
        item = self._find_item(item_id)
        if item is None:
            return
 
        if self.confirm_remove_var.get():
            name = f"{item['artist']} - {item['title']}" if item["artist"] else item["title"]
            if not messagebox.askyesno("Remove song", f"Remove '{name}' from the queue?"):
                return
 
        self.queue.remove(item)
        if self.queue_tree.exists(item_id):
            self.queue_tree.delete(item_id)
        self.status_var.set(f"{len(self.queue)} song(s) in queue.")
 
    def _clear_completed_queue(self):
        to_remove = [it for it in self.queue if it["status"] in ("Complete", "Skipped")]
        for item in to_remove:
            if self.queue_tree.exists(item["id"]):
                self.queue_tree.delete(item["id"])
        self.queue = [it for it in self.queue if it not in to_remove]
        self.status_var.set(f"{len(self.queue)} song(s) in queue.")
 
    # ========================================================
    # AUTO-DOWNLOAD PROCESSING
    # ========================================================
 
    def _maybe_start_processing(self):
        if self.downloading:
            return
 
        if not any(it["status"] == "Waiting" for it in self.queue):
            return
 
        if yt_dlp is None:
            messagebox.showerror("Missing dependency", "yt-dlp is not installed.\n\npip install yt-dlp")
            return
 
        if not find_ffmpeg():
            messagebox.showerror(
                "FFmpeg not found",
                "FFmpeg is required.\n\nInstall it and make sure ffmpeg is on PATH."
            )
            return
 
        self.downloading = True
        threading.Thread(target=self._process_queue, daemon=True).start()
 
    def _process_queue(self):
        while True:
            item = next((it for it in self.queue if it["status"] == "Waiting"), None)
            if item is None:
                break
 
            item_id = item["id"]
 
            if self.skip_existing_var.get():
                expected = self._expected_output_path(item)
                if os.path.exists(expected):
                    self._update_item(item_id, status="Skipped", progress=100)
                    continue
 
            self.current_item_id = item_id
            self._update_item(item_id, status="Downloading", progress=0)
 
            try:
                mp3_path = self._download_item(item, item_id)
                self._tag_mp3(mp3_path, item)
                self._update_item(item_id, status="Complete", progress=100)
 
            except Exception as e:
                self._update_item(item_id, status="Error", progress=0, error=str(e))
 
            self.current_item_id = None
 
        self.root.after(0, self._queue_finished)
        self.root.after(0, self._refresh_grid)
 
    def _expected_output_path(self, item):
        artist = safe_filename(item.get("artist"))
        title = safe_filename(item.get("title"))
 
        filename = f"{artist} - {title}" if artist and artist != "Unknown" else title
        filename = safe_filename(filename)
        return os.path.join(self.output_dir, filename + ".mp3")
 
    def _download_item(self, item, item_id):
        expected_mp3 = self._expected_output_path(item)
        base_no_ext = os.path.splitext(expected_mp3)[0]
        outtmpl = base_no_ext + ".%(ext)s"
 
        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
 
                if total:
                    percent = (downloaded / total) * 100
                    self._update_item(item_id, status="Downloading", progress=percent)
                    self.root.after(
                        0,
                        lambda p=percent: self.status_var.set(
                            f"Downloading '{item.get('title', '')}' - {int(p)}%"
                        )
                    )
 
            elif d["status"] == "finished":
                self._update_item(item_id, status="Converting", progress=99)
                self.root.after(
                    0,
                    lambda: self.status_var.set(f"Converting '{item.get('title', '')}' to MP3...")
                )
 
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.quality_var.get() or "320",
                }
            ],
            "postprocessor_args": ["-ar", self.sample_rate_var.get() or "48000"],
        }
 
        os.makedirs(self.output_dir, exist_ok=True)
 
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(item["url"], download=True)
            base = ydl.prepare_filename(info)
 
        mp3_path = os.path.splitext(base)[0] + ".mp3"
 
        if not os.path.exists(mp3_path):
            raise FileNotFoundError(f"MP3 was not created:\n{mp3_path}")
 
        return mp3_path
 
    def _update_item(self, item_id, status=None, progress=None, error=None):
        item = self._find_item(item_id)
        if item is None:
            return
 
        if status is not None:
            item["status"] = status
        if progress is not None:
            item["progress"] = progress
        if error is not None:
            item["error"] = error
 
        self.root.after(0, lambda iid=item_id: self._update_queue_row(iid))
 
    def _queue_finished(self):
        self.downloading = False
        self.current_item_id = None
 
        completed = sum(1 for item in self.queue if item.get("status") in ("Complete", "Skipped"))
        errors = sum(1 for item in self.queue if item.get("status") == "Error")
 
        if errors:
            self.status_var.set(f"Queue finished - {completed} done, {errors} failed.")
        else:
            self.status_var.set(f"Queue finished - {completed} song(s) done.")
 
    # ========================================================
    # TAGGING
    # ========================================================
 
    def _tag_mp3(self, mp3_path, item):
        self._apply_id3_tags(
            mp3_path,
            item.get("artist", ""),
            item.get("title", ""),
            item.get("album", ""),
            item.get("year", ""),
            item.get("genre", ""),
            thumbnail_url=item.get("thumbnail"),
            track=item.get("track", ""),
        )
 
    def _apply_id3_tags(self, mp3_path, artist, title, album, year, genre, thumbnail_url=None, track=""):
        if ID3 is None:
            raise RuntimeError("mutagen is not installed")
 
        if not os.path.exists(mp3_path):
            raise FileNotFoundError(mp3_path)
 
        try:
            audio = ID3(mp3_path)
        except ID3Error:
            audio = ID3()
 
        artist = (artist or "").strip()
        title = (title or "").strip()
        album = (album or "").strip()
        year = (year or "").strip()
        genre = (genre or "").strip()
        track = (track or "").strip()
 
        if artist:
            audio["TPE1"] = TPE1(encoding=3, text=artist)
        if title:
            audio["TIT2"] = TIT2(encoding=3, text=title)
        if album:
            audio["TALB"] = TALB(encoding=3, text=album)
        if year:
            audio["TDRC"] = TDRC(encoding=3, text=year)
        if genre:
            audio["TCON"] = TCON(encoding=3, text=genre)
        if track:
            audio["TRCK"] = TRCK(encoding=3, text=track)
 
        if thumbnail_url and self.auto_thumbnail_var.get():
            try:
                thumbnail = self._download_thumbnail(thumbnail_url, mp3_path)
                if thumbnail:
                    with open(thumbnail, "rb") as img:
                        data = img.read()
                    audio["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=data)
                    try:
                        os.remove(thumbnail)
                    except OSError:
                        pass
            except Exception:
                pass
 
        audio.save(mp3_path, v2_version=3)
 
    def _download_thumbnail(self, url, mp3_path):
        if not url:
            return None
 
        base = os.path.splitext(mp3_path)[0]
        path = base + "_cover.jpg"
 
        try:
            import urllib.request
            urllib.request.urlretrieve(url, path)
            return path
        except Exception:
            return None
 
    # ========================================================
    # DOWNLOAD-FOLDER GRID (browse + edit tags)
    # ========================================================
 
    def _refresh_grid(self):
        folder = self.output_dir
 
        if not os.path.isdir(folder):
            self._import_files = []
        else:
            try:
                self._import_files = [
                    os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".mp3")
                ]
            except OSError:
                self._import_files = []
 
        self._redraw_grid()
 
    def _redraw_grid(self):
        if not hasattr(self, "grid_tree"):
            return
 
        for iid in self.grid_tree.get_children():
            self.grid_tree.delete(iid)
 
        query = self.filter_var.get().lower().strip() if hasattr(self, "filter_var") else ""
 
        for path in sorted(self._import_files, key=lambda p: os.path.basename(p).lower()):
            if query and query not in os.path.basename(path).lower():
                continue
 
            tags = self._read_id3_tags(path)
            display_title = tags["title"] or os.path.splitext(os.path.basename(path))[0]
            tag_label = self._read_tag_version_label(path)
            filename = os.path.basename(path)
            directory = os.path.dirname(path) + os.sep
 
            self.grid_tree.insert(
                "", "end", iid=path,
                values=(filename, directory, tag_label, display_title,
                        tags["artist"], tags["album"], tags["track"])
            )
 
        self._update_stats_label()
 
    def _sort_grid(self, col):
        reverse = self._sort_reverse.get(col, False)
        items = [(self.grid_tree.set(k, col), k) for k in self.grid_tree.get_children("")]
        items.sort(key=lambda t: t[0].lower(), reverse=reverse)
        for index, (_, k) in enumerate(items):
            self.grid_tree.move(k, "", index)
        self._sort_reverse[col] = not reverse
 
    def _read_id3_tags(self, path):
        result = {
            "artist": "", "title": "", "album": "", "year": "", "genre": "", "track": "",
        }
 
        if ID3 is None:
            return result
 
        try:
            audio = ID3(path)
            result["artist"] = str(audio.get("TPE1", ""))
            result["title"] = str(audio.get("TIT2", ""))
            result["album"] = str(audio.get("TALB", ""))
            result["year"] = str(audio.get("TDRC", ""))
            result["genre"] = str(audio.get("TCON", ""))
            result["track"] = str(audio.get("TRCK", ""))
        except Exception:
            pass
 
        return result
 
    def _read_tag_version_label(self, path):
        has_v1 = False
        try:
            with open(path, "rb") as f:
                f.seek(-128, os.SEEK_END)
                has_v1 = f.read(3) == b"TAG"
        except Exception:
            has_v1 = False
 
        v2_label = None
        if ID3 is not None:
            try:
                audio = ID3(path)
                v = audio.version
                v2_label = f"ID3v2.{v[1]}" if len(v) > 1 else "ID3v2"
            except Exception:
                v2_label = None
 
        if v2_label and has_v1:
            return f"{v2_label} + ID3v1"
        if v2_label:
            return v2_label
        if has_v1:
            return "ID3v1"
        return "No Tag"
 
    def _compute_stats(self):
        count = len(self._import_files)
        total_bytes = 0
        total_seconds = 0.0
 
        for path in self._import_files:
            try:
                total_bytes += os.path.getsize(path)
            except OSError:
                pass
            if MP3Info is not None:
                try:
                    total_seconds += MP3Info(path).info.length
                except Exception:
                    pass
 
        return count, total_bytes, total_seconds
 
    @staticmethod
    def _format_duration(seconds):
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
 
    def _update_stats_label(self):
        if not hasattr(self, "stats_var"):
            return
        count, total_bytes, total_seconds = self._compute_stats()
        size_mb = total_bytes / (1024 * 1024)
        duration = self._format_duration(total_seconds)
        self.stats_var.set(f"{count} song(s) - {duration} - {size_mb:.1f} MB")
 
    # ---- selecting a row loads it for editing ----
 
    def _on_grid_select(self, _event=None):
        selected = self.grid_tree.selection()
        if not selected:
            return
 
        path = selected[0]
        self.selected_import_path = path
 
        tags = self._read_id3_tags(path)
        self.field_title.set(tags["title"])
        self.field_artist.set(tags["artist"])
        self.field_album.set(tags["album"])
        self.field_year.set(tags["year"])
        self.field_track.set(tags["track"])
        self.field_genre.set(tags["genre"])
 
        self.url_entry.delete(0, tk.END)
        self._prefetch_seen_url = ""
 
        self._refresh_left_action_button()
        self.status_var.set(f"Editing: {os.path.basename(path)}")
 
    def _refresh_left_action_button(self):
        if self.selected_import_path:
            self.left_action_button.config(text="Save Tags", command=self._save_selected_tags)
        else:
            self.left_action_button.config(text="Add Song to Queue", command=self.add_to_queue)
 
    def _save_selected_tags(self):
        path = self.selected_import_path
 
        if not path or not os.path.exists(path):
            self.status_var.set("Select a song from the list first.")
            return
 
        if ID3 is None:
            self.status_var.set("mutagen is not installed -- run: pip install mutagen")
            return
 
        try:
            self._apply_id3_tags(
                path,
                self.field_artist.get().strip(),
                self.field_title.get().strip(),
                self.field_album.get().strip(),
                self.field_year.get().strip(),
                self.field_genre.get().strip(),
                track=self.field_track.get().strip(),
            )
            self._redraw_grid()
            self.status_var.set(f"Saved tags for {os.path.basename(path)}")
        except Exception as e:
            self.status_var.set(f"Error saving tags: {e}")
 
        self.selected_import_path = None
        if self.grid_tree.selection():
            self.grid_tree.selection_remove(self.grid_tree.selection())
        self._clear_metadata_fields()
        self._refresh_left_action_button()
 
 
# ============================================================
# MAIN
# ============================================================
 
def main():
    root = tk.Tk()
    app = YTMp3ConverterApp(root)
    root.mainloop()
 
 
if __name__ == "__main__":
    main()
 
