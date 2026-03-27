#!/usr/bin/env python3
"""
Meeting Recorder & Notes Generator — Powered by Liljedahl Legal Tech
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, ttk
import threading
import queue
import os
import time
import wave
import tempfile
import json
from datetime import datetime
import numpy as np
try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

_KEYRING_SERVICE  = "MeetingRecorder-LLT"
_KEYRING_USERNAME = "anthropic_api_key"
CONFIG_PATH       = os.path.expanduser("~/.meeting_recorder_llt.json")

SAMPLE_RATE   = 16000
CHANNELS      = 1
CHUNK_SECONDS = 20

# ── Colour palette ───────────────────────────────────────────────────────────
BG      = "#0E0D0C"
BG2     = "#161412"
BG3     = "#1E1B18"
BG4     = "#272320"
BORDER  = "#332E28"
BORDER2 = "#4A4238"
FG      = "#F2EEE8"   # primary text — warm white
FG2     = "#C8B89A"   # secondary text — field labels, section headers
FG3     = "#E0D4C0"   # emphasized text — transcript content
FG_DIM  = "#9A8A72"   # tertiary — hints, "Powered by", tab inactive
ACCENT  = "#E07820"   # orange brand accent
ACCENT2 = "#C05E0A"   # darker orange for hover/active
RED     = "#D95050"
GREEN   = "#4AB870"

# ── Fonts ────────────────────────────────────────────────────────────────────
FONT_LOGO1   = ("Helvetica Neue", 14, "bold")
FONT_LOGO2   = ("Helvetica Neue", 14)
FONT_POWERED = ("Helvetica Neue", 9, "italic")
FONT_SECTION = ("Helvetica Neue", 8, "bold")
FONT_H       = ("Helvetica Neue", 11, "bold")
FONT_B       = ("Helvetica Neue", 11)
FONT_S       = ("Helvetica Neue", 10)
FONT_XS      = ("Helvetica Neue", 9)
FONT_M       = ("Menlo", 10)
FONT_MS      = ("Menlo", 9)
FONT_TIMER   = ("Menlo", 12)
FONT_GEAR    = ("Helvetica Neue", 18)


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class RoundedButton(tk.Canvas):
    """Canvas-based button with smooth rounded corners and full colour control."""

    def __init__(self, parent, text, command=None, style="solid",
                 bg=None, fg="#FFFFFF", radius=12,
                 font_spec=None, padx=28, pady=12,
                 state="normal", fixed_width=None):
        import tkinter.font as tkfont

        self._style    = style          # "solid" or "ghost"
        self._bg       = bg or ACCENT
        self._fg       = fg
        self._radius   = radius
        self._padx     = padx
        self._pady     = pady
        self._command  = command
        self._enabled  = (state == "normal")
        self._text     = text
        self._hovering = False
        self._fspec    = font_spec or ("Helvetica Neue", 13)

        weight = "bold" if len(self._fspec) > 2 and "bold" in self._fspec[2] else "normal"
        mf = tkfont.Font(family=self._fspec[0], size=self._fspec[1], weight=weight)
        th = mf.metrics("linespace")
        tw = mf.measure(text)
        self._btn_w = fixed_width or (tw + 2 * padx)
        self._btn_h = th + 2 * pady

        super().__init__(parent, width=self._btn_w, height=self._btn_h,
                         bg=BG, highlightthickness=0, bd=0)
        self._draw()
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>",    self._on_enter)
        self.bind("<Leave>",    self._on_leave)

    # ── drawing ───────────────────────────────────────────────────────────────

    def _resolve_fill(self):
        if not self._enabled:
            return (BG3, FG_DIM) if self._style == "solid" else (BG, BORDER)
        if self._hovering:
            if self._style == "solid":
                c = self._bg.lstrip("#")
                r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
                darker = f"#{int(r*.82):02x}{int(g*.82):02x}{int(b*.82):02x}"
                return darker, self._fg
            else:
                return BG2, self._fg
        if self._style == "solid":
            return self._bg, self._fg
        return BG, self._fg

    def _draw(self):
        self.delete("all")
        w, h, r = self._btn_w, self._btn_h, self._radius
        fill, fg = self._resolve_fill()
        outline = fg if self._style == "ghost" else fill

        # Smooth rounded-rectangle polygon
        pts = [r, 0,  w-r, 0,  w, 0,  w, r,
               w, h-r,  w, h,  w-r, h,  r, h,
               0, h,  0, h-r,  0, r,  0, 0]
        self.create_polygon(pts, smooth=True,
                            fill=fill, outline=outline, width=1)
        self.create_text(w // 2, h // 2, text=self._text,
                         font=self._fspec, fill=fg, anchor="center")

    # ── public interface ──────────────────────────────────────────────────────

    def config(self, **kw):
        import tkinter.font as tkfont
        changed = False
        if "text" in kw:
            self._text = kw.pop("text")
            changed = True
        if "state" in kw:
            self._enabled = (kw.pop("state") == "normal")
            changed = True
        if "bg" in kw:
            self._bg = kw.pop("bg")
            changed = True
        if "fg" in kw:
            self._fg = kw.pop("fg")
            changed = True
        if "cursor" in kw:
            super().config(cursor=kw.pop("cursor"))
        if kw:
            super().config(**kw)
        if changed:
            self._draw()

    def cget(self, key):
        if key == "state":  return "normal" if self._enabled else "disabled"
        if key == "text":   return self._text
        if key == "bg":     return self._bg
        return super().cget(key)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_click(self, _=None):
        if self._enabled and self._command:
            self._command()

    def _on_enter(self, _=None):
        self._hovering = True;  self._draw()

    def _on_leave(self, _=None):
        self._hovering = False; self._draw()


def list_audio_devices():
    try:
        import sounddevice as sd
        devs = []
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                devs.append({"index": i, "name": d["name"], "channels": d["max_input_channels"]})
        return devs
    except Exception:
        return []


def _set_macos_app_name():
    try:
        from Foundation import NSProcessInfo, NSBundle
        NSProcessInfo.processInfo().setProcessName_("Meeting Recorder")
        bundle = NSBundle.mainBundle()
        for d in filter(None, [bundle.localizedInfoDictionary(),
                                bundle.infoDictionary()]):
            d["CFBundleName"]        = "Meeting Recorder"
            d["CFBundleDisplayName"] = "Meeting Recorder"
    except Exception:
        pass


class MeetingRecorder(tk.Tk):
    def __init__(self):
        _set_macos_app_name()
        super().__init__()
        self.title("Meeting Recorder")
        self.configure(bg=BG)
        self.geometry("920x880")
        self.minsize(780, 720)
        self.resizable(True, True)

        self._config   = load_config()
        self.user_name = self._config.get("user_name", "")

        self.api_key        = tk.StringVar()
        self.meeting_title  = tk.StringVar()
        self.participants   = tk.StringVar()
        self.language       = tk.StringVar(value="sv")
        self.mic_device_idx = tk.IntVar(value=-1)
        self.whisper_size   = tk.StringVar(value="medium")
        self.save_format    = tk.StringVar(value="md")

        self.recording              = False
        self.audio_chunks           = []
        self.transcript_parts       = []
        self.rec_thread             = None
        self.log_q                  = queue.Queue()
        self.whisper_model          = None
        self._loaded_whisper_size   = None
        self.diarization_pipeline   = None
        self.anthropic_client       = None
        self.total_seconds          = 0
        self.timer_id               = None
        self.recording_start_time   = None   # set when recording begins
        self._devices               = []

        self.transcription_queue          = queue.Queue()
        self.pending_transcriptions       = 0
        self._transcription_worker_thread = None

        self._build_ui()
        self._load_saved_key()
        self._poll_log()
        self.after(200, self._refresh_devices)
        threading.Thread(target=self._preload_whisper, daemon=True).start()

        if not self.user_name:
            self.after(300, self._show_setup_dialog)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_config()
        self._build_audio_source()
        self._build_buttons()
        self._build_tabs()
        self._build_status()

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG, padx=32, pady=20)
        hdr.pack(fill="x")

        left = tk.Frame(hdr, bg=BG)
        left.pack(side="left", fill="y")

        name_row = tk.Frame(left, bg=BG)
        name_row.pack(anchor="w")
        self._logo_name_lbl = tk.Label(
            name_row, text=self._display_name(),
            font=FONT_LOGO1, bg=BG, fg=FG)
        self._logo_name_lbl.pack(side="left")
        tk.Label(name_row, text="  Meeting Recorder",
                 font=FONT_LOGO2, bg=BG, fg=FG2).pack(side="left")

        tk.Label(left, text="Powered by Liljedahl Legal Tech",
                 font=FONT_POWERED, bg=BG, fg=FG_DIM).pack(anchor="w", pady=(3, 0))

        right = tk.Frame(hdr, bg=BG)
        right.pack(side="right", fill="y")

        self.timer_lbl = tk.Label(right, text="00:00:00",
                                  font=FONT_TIMER, bg=BG, fg=FG_DIM)
        self.timer_lbl.pack(side="right", padx=(16, 0))

        # Gear — Label, no border
        gear = tk.Label(right, text="⚙", font=FONT_GEAR,
                        bg=BG, fg=FG_DIM, cursor="hand2")
        gear.pack(side="right")
        gear.bind("<Enter>",  lambda _: gear.config(fg=FG))
        gear.bind("<Leave>",  lambda _: gear.config(fg=FG_DIM))
        gear.bind("<Button-1>", lambda _: self._show_settings_dialog())

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    def _build_config(self):
        outer = tk.Frame(self, bg=BG, padx=32, pady=20)
        outer.pack(fill="x")
        self._section_label(outer, "KONFIGURATION")
        card = self._card(outer)

        def field(parent, label, var, show=None, hint=None):
            row = tk.Frame(parent, bg=BG2)
            row.pack(fill="x", pady=6)
            tk.Label(row, text=label, font=FONT_S, bg=BG2, fg=FG2,
                     width=16, anchor="w").pack(side="left")
            kw = dict(textvariable=var, font=FONT_M, bg=BG3, fg=FG,
                      insertbackground=FG, relief="flat", bd=0,
                      highlightthickness=1, highlightbackground=BORDER2,
                      highlightcolor=ACCENT)
            if show:
                kw["show"] = show
            e = tk.Entry(row, **kw)
            e.pack(side="left", fill="x", expand=True, ipady=7)
            if hint:
                tk.Label(row, text=hint, font=FONT_XS,
                         bg=BG2, fg=FG_DIM).pack(side="left", padx=(10, 0))
            return e, row

        self._key_entry, r1 = field(card, "API-nyckel", self.api_key, show="•")
        tk.Button(r1, text="visa", font=FONT_XS,
                  bg=BG4, fg=FG2, relief="flat", bd=0, cursor="hand2",
                  padx=10, pady=4, activebackground=BORDER2, activeforeground=FG,
                  command=lambda: self._key_entry.config(
                      show="" if self._key_entry.cget("show") == "•" else "•")
                  ).pack(side="left", padx=(6, 0))

        field(card, "Möte / titel", self.meeting_title)
        field(card, "Deltagare", self.participants,
              hint="namn, roll — kommaseparerade")

        # Language row
        lang_row = tk.Frame(card, bg=BG2)
        lang_row.pack(fill="x", pady=6)
        tk.Label(lang_row, text="Språk", font=FONT_S, bg=BG2, fg=FG2,
                 width=16, anchor="w").pack(side="left")
        for val, lbl in [("sv", "Svenska"), ("en", "English")]:
            tk.Radiobutton(lang_row, text=lbl, variable=self.language, value=val,
                           font=FONT_S, bg=BG3, fg=FG, selectcolor=ACCENT,
                           activebackground=BG4, activeforeground=FG,
                           indicatoron=False, relief="solid", bd=1,
                           padx=10, pady=3, cursor="hand2").pack(side="left", padx=(0, 6))

        # Whisper model row
        model_row = tk.Frame(card, bg=BG2)
        model_row.pack(fill="x", pady=6)
        tk.Label(model_row, text="Transkription", font=FONT_S, bg=BG2, fg=FG2,
                 width=16, anchor="w").pack(side="left")
        for val, lbl, hint in [
            ("small",    "Small",    "snabb"),
            ("medium",   "Medium",   "balanserad"),
            ("large-v3", "Large v3", "bäst kvalitet"),
        ]:
            grp = tk.Frame(model_row, bg=BG2)
            grp.pack(side="left", padx=(0, 6))
            tk.Radiobutton(grp, text=f"{lbl}  ({hint})", variable=self.whisper_size, value=val,
                           font=FONT_S, bg=BG3, fg=FG, selectcolor=ACCENT,
                           activebackground=BG4, activeforeground=FG,
                           indicatoron=False, relief="solid", bd=1,
                           padx=10, pady=3, cursor="hand2").pack(side="left")

    def _build_audio_source(self):
        outer = tk.Frame(self, bg=BG, padx=32, pady=4)
        outer.pack(fill="x")
        self._section_label(outer, "MIKROFON")
        card = self._card(outer)

        tk.Label(card, text="Enhet", font=FONT_S, bg=BG2, fg=FG2).pack(anchor="w", pady=(0, 6))

        combo_row = tk.Frame(card, bg=BG2)
        combo_row.pack(fill="x")

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Dark.TCombobox",
                        fieldbackground=BG3, background=BG4,
                        foreground=FG, selectbackground=BG3,
                        selectforeground=FG, bordercolor=BORDER2,
                        arrowcolor=ACCENT, relief="flat", padding=8)
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", BG3), ("disabled", BG2)],
                  selectbackground=[("readonly", BG3)],
                  foreground=[("readonly", FG), ("disabled", FG2)],
                  selectforeground=[("readonly", FG)],
                  arrowcolor=[("readonly", ACCENT)])

        self._mic_combo = ttk.Combobox(combo_row, state="readonly",
                                        font=FONT_MS, style="Dark.TCombobox")
        self._mic_combo.pack(side="left", fill="x", expand=True)
        self._mic_combo.bind("<<ComboboxSelected>>", self._on_mic_select)

        tk.Button(combo_row, text="↺", font=("Helvetica Neue", 13),
                  bg=BG3, fg=FG2, relief="flat", bd=0, cursor="hand2",
                  padx=12, pady=3, activebackground=BG4, activeforeground=FG,
                  command=self._refresh_devices).pack(side="left", padx=(8, 0))

    def _build_buttons(self):
        outer = tk.Frame(self, bg=BG, padx=32, pady=20)
        outer.pack(fill="x")

        btn_row = tk.Frame(outer, bg=BG)
        btn_row.pack(fill="x")

        self.rec_btn = RoundedButton(
            btn_row, text="⬤  Starta inspelning",
            style="solid", bg=ACCENT, fg="#FFFFFF",
            font_spec=("Helvetica Neue", 13, "bold"),
            padx=28, pady=13, radius=12,
            command=self._toggle_recording,
        )
        self.rec_btn.pack(side="left", padx=(0, 10))

        self.notes_btn = RoundedButton(
            btn_row, text="◆  Generera anteckningar",
            style="ghost", fg=FG_DIM,
            font_spec=("Helvetica Neue", 13),
            padx=24, pady=13, radius=12,
            state="disabled", command=self._generate_notes,
            fixed_width=240,
        )
        self.notes_btn.pack(side="left", padx=(0, 10))

        self.save_btn = RoundedButton(
            btn_row, text="↓  Spara",
            style="ghost", fg=FG_DIM,
            font_spec=("Helvetica Neue", 13),
            padx=24, pady=13, radius=12,
            state="disabled", command=self._save_output,
        )
        self.save_btn.pack(side="left")

        # Format selector — own row, clearly separated
        fmt_row = tk.Frame(outer, bg=BG)
        fmt_row.pack(fill="x", pady=(12, 0))

        tk.Label(fmt_row, text="Exportformat", font=FONT_XS,
                 bg=BG, fg=FG2).pack(side="left", padx=(2, 14))

        for val, lbl, desc in [
            ("md",   ".md",   "Markdown"),
            ("docx", ".docx", "Word"),
            ("pdf",  ".pdf",  "PDF"),
        ]:
            btn = tk.Radiobutton(
                fmt_row, text=f"{lbl}  {desc}",
                variable=self.save_format, value=val,
                font=FONT_S, bg=BG3, fg=FG, selectcolor=ACCENT,
                activebackground=BG4, activeforeground=FG,
                indicatoron=False, relief="solid", bd=1,
                padx=10, pady=3, cursor="hand2")
            btn.pack(side="left", padx=(0, 6))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    def _build_tabs(self):
        tab_bar = tk.Frame(self, bg=BG, padx=32)
        tab_bar.pack(fill="x")
        self.active_tab = tk.StringVar(value="transcript")
        for label, key in [("Transkript", "transcript"),
                            ("Mötesanteckningar", "notes"),
                            ("Log", "log")]:
            tk.Radiobutton(tab_bar, text=label, variable=self.active_tab, value=key,
                           font=FONT_B, bg=BG, fg=FG2, selectcolor=BG,
                           activebackground=BG, activeforeground=FG,
                           indicatoron=False, relief="flat", bd=0,
                           padx=18, pady=12, cursor="hand2",
                           command=self._switch_tab).pack(side="left")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        self.text_frame = tk.Frame(self, bg=BG, padx=32, pady=14)
        self.text_frame.pack(fill="both", expand=True)

        kw = dict(bg=BG2, fg=FG3, insertbackground=FG, relief="flat", bd=0,
                  wrap="word", state="disabled", selectbackground=BORDER2,
                  highlightthickness=1, highlightbackground=BORDER)
        self.transcript_box = scrolledtext.ScrolledText(self.text_frame, font=FONT_M, **kw)
        self.notes_box      = scrolledtext.ScrolledText(self.text_frame, font=FONT_B, **kw)
        self.log_box        = scrolledtext.ScrolledText(
            self.text_frame, font=FONT_MS, fg=FG2,
            **{k: v for k, v in kw.items() if k not in ("fg",)})
        self.transcript_box.pack(fill="both", expand=True)
        self._switch_tab()

    def _build_status(self):
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        self.status_var = tk.StringVar(value="Redo.")
        bar = tk.Frame(self, bg=BG2)
        bar.pack(fill="x")
        tk.Label(bar, textvariable=self.status_var, font=FONT_XS,
                 bg=BG2, fg=FG2, anchor="w", padx=32, pady=8).pack(side="left")
        tk.Label(bar, text="Powered by Liljedahl Legal Tech",
                 font=FONT_POWERED, bg=BG2, fg=FG_DIM, padx=32, pady=8).pack(side="right")

    # ── UI helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _section_label(parent, text):
        tk.Label(parent, text=text, font=FONT_SECTION,
                 bg=BG, fg=FG2).pack(anchor="w", pady=(0, 10))

    @staticmethod
    def _card(parent):
        card = tk.Frame(parent, bg=BG2, padx=22, pady=18,
                        highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", pady=(0, 4))
        return card

    def _display_name(self) -> str:
        return self.user_name if self.user_name else "Meeting"

    def _switch_tab(self):
        for w in (self.transcript_box, self.notes_box, self.log_box):
            w.pack_forget()
        {"transcript": self.transcript_box, "notes": self.notes_box,
         "log": self.log_box}[self.active_tab.get()].pack(fill="both", expand=True)

    def _set_status(self, msg): self.status_var.set(msg)
    def _log(self, msg): self.log_q.put(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _poll_log(self):
        while not self.log_q.empty():
            self._append(self.log_box, self.log_q.get() + "\n")
        self.after(200, self._poll_log)

    def _append(self, widget, text, color=None):
        widget.config(state="normal")
        if color:
            tag = f"c{color.replace('#','')}"
            widget.tag_config(tag, foreground=color)
            widget.insert("end", text, tag)
        else:
            widget.insert("end", text)
        widget.see("end")
        widget.config(state="disabled")

    def _clear(self, widget):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.config(state="disabled")

    # ── Key management ────────────────────────────────────────────────────────

    def _load_saved_key(self):
        """Load API key from keychain only — never from environment variables."""
        if _KEYRING_AVAILABLE:
            try:
                saved = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
                if saved:
                    self.api_key.set(saved)
                    self._log("API-nyckel laddad från Keychain.")
                    return
            except Exception:
                pass
        self._log("Ingen sparad API-nyckel hittades.")

    def _save_key_to_keychain(self, key: str):
        if _KEYRING_AVAILABLE:
            try:
                keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, key)
            except Exception:
                pass

    # ── First-run / settings dialogs ─────────────────────────────────────────

    def _show_setup_dialog(self):
        self._open_name_dialog(
            title="Välkommen till Meeting Recorder",
            message="Ange ditt namn eller företagsnamn.\nDet används i mötesanteckningar och exporterade filer.",
            is_first_run=True,
        )

    def _show_settings_dialog(self):
        self._open_name_dialog(
            title="Inställningar",
            message="Ändra namn eller företagsnamn:",
            is_first_run=False,
        )

    def _open_name_dialog(self, title: str, message: str, is_first_run: bool):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width()  - 440) // 2
        y = self.winfo_y() + (self.winfo_height() - 240) // 2
        dlg.geometry(f"440x240+{x}+{y}")

        pad = tk.Frame(dlg, bg=BG, padx=36, pady=32)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text=title, font=("Helvetica Neue", 13, "bold"),
                 bg=BG, fg=FG).pack(anchor="w")
        tk.Label(pad, text=message, font=FONT_S, bg=BG, fg=FG2,
                 wraplength=368, justify="left").pack(anchor="w", pady=(8, 18))

        entry_var = tk.StringVar(value=self.user_name)
        entry = tk.Entry(pad, textvariable=entry_var, font=FONT_M,
                         bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=0,
                         highlightthickness=1, highlightbackground=BORDER2,
                         highlightcolor=ACCENT)
        entry.pack(fill="x", ipady=9)
        entry.focus_set()
        entry.select_range(0, "end")

        btn_row = tk.Frame(pad, bg=BG)
        btn_row.pack(fill="x", pady=(18, 0))

        def save():
            name = entry_var.get().strip()
            if not name:
                entry.config(highlightbackground=RED)
                return
            self.user_name = name
            self._config["user_name"] = name
            save_config(self._config)
            self._logo_name_lbl.config(text=self._display_name())
            dlg.destroy()

        save_lbl = tk.Label(btn_row, text="Spara", font=FONT_B,
                             bg=ACCENT, fg="#FFFFFF", padx=24, pady=8, cursor="hand2")
        save_lbl.pack(side="right")
        save_lbl.bind("<Button-1>", lambda _: save())
        save_lbl.bind("<Enter>",  lambda _: save_lbl.config(bg=ACCENT2))
        save_lbl.bind("<Leave>",  lambda _: save_lbl.config(bg=ACCENT))

        if not is_first_run:
            cancel_lbl = tk.Label(btn_row, text="Avbryt", font=FONT_B,
                                   bg=BG3, fg=FG2, padx=24, pady=8, cursor="hand2")
            cancel_lbl.pack(side="right", padx=(0, 8))
            cancel_lbl.bind("<Button-1>", lambda _: dlg.destroy())
            cancel_lbl.bind("<Enter>", lambda _: cancel_lbl.config(bg=BG4, fg=FG))
            cancel_lbl.bind("<Leave>", lambda _: cancel_lbl.config(bg=BG3, fg=FG2))

        entry.bind("<Return>", lambda _: save())
        dlg.protocol("WM_DELETE_WINDOW", save if is_first_run else dlg.destroy)
        dlg.wait_window()

    # ── Device handling ───────────────────────────────────────────────────────

    def _refresh_devices(self):
        self._devices = list_audio_devices()
        if not self._devices:
            self._set_status("sounddevice ej tillgängligt")
            return
        names = [f"{d['name']}  [{d['index']}]" for d in self._devices]
        self._mic_combo["values"] = names
        if self._devices:
            self._mic_combo.current(0)
            self.mic_device_idx.set(self._devices[0]["index"])
        self._log(f"{len(self._devices)} enheter hittade.")

    def _on_mic_select(self, _=None):
        idx = self._mic_combo.current()
        if idx >= 0:
            self.mic_device_idx.set(self._devices[idx]["index"])

    # ── Whisper loading ───────────────────────────────────────────────────────

    def _preload_whisper(self):
        size = self.whisper_size.get()
        self.after(0, lambda: self._set_rec_btn_enabled(False))
        try:
            from faster_whisper import WhisperModel
            from pyannote.audio import Pipeline
            self._log(f"Förladdar Whisper {size}…")
            self.after(0, lambda: self._set_status(
                f"Laddar Whisper {size}…  (inspelningsknappen aktiveras när den är klar)"))
            self.whisper_model = WhisperModel(size, device="cpu", compute_type="int8")
            self._loaded_whisper_size = size
            self._log("Whisper redo. Laddar talarseparation…")
            hf_token = os.environ.get("HF_TOKEN", "")
            if hf_token:
                self.diarization_pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1", token=hf_token)
                self._log("Talarseparation redo.")
            else:
                self._log("HF_TOKEN saknas — talarseparation inaktiverad.")
            self.after(0, lambda: self._set_status(
                f"Redo  —  Whisper {size}" +
                (" + talarseparation" if self.diarization_pipeline else "") + " laddat."))
        except Exception as e:
            import traceback
            self._log(f"Förladdningsfel: {e}")
            self._log(traceback.format_exc())
            self.after(0, lambda: self._set_status("Redo (whisper ej förladdad)"))
        finally:
            self.after(0, lambda: self._set_rec_btn_enabled(True))

    def _load_whisper(self):
        size = self.whisper_size.get()
        try:
            from faster_whisper import WhisperModel
            self._log(f"Laddar Whisper {size}…")
            self.whisper_model = WhisperModel(size, device="cpu", compute_type="int8")
            self._loaded_whisper_size = size
            self._log("Whisper klar.")
            self.after(0, self._do_start)
        except Exception as e:
            self._log(f"Whisper-fel: {e}")
            self.after(0, lambda: messagebox.showerror("Whisper-fel", str(e)))

    # ── Recording flow ────────────────────────────────────────────────────────

    def _set_rec_btn_enabled(self, enabled: bool):
        self.rec_btn.config(state="normal" if enabled else "disabled")

    def _toggle_recording(self):
        if not self.recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        key = self.api_key.get().strip()
        if not key:
            messagebox.showerror("API-nyckel saknas", "Fyll i Anthropic API-nyckel.")
            return
        try:
            import anthropic as ac
            self.anthropic_client = ac.Anthropic(api_key=key)
        except Exception as e:
            messagebox.showerror("Fel", str(e))
            return
        self._save_key_to_keychain(key)
        if self.mic_device_idx.get() < 0:
            messagebox.showerror("Ingen mikrofon", "Välj en mikrofonenhet.")
            return
        if self.whisper_model is None or self._loaded_whisper_size != self.whisper_size.get():
            self._set_status(f"Laddar Whisper {self.whisper_size.get()}…")
            self.update()
            threading.Thread(target=self._load_whisper, daemon=True).start()
            return
        self._do_start()

    def _do_start(self):
        self.recording = True
        self.audio_chunks = []
        self.transcript_parts = []
        self.total_seconds = 0
        self.recording_start_time = datetime.now()
        self.pending_transcriptions = 0
        self._clear(self.transcript_box)
        self._clear(self.notes_box)

        self.transcription_queue = queue.Queue()
        self._transcription_worker_thread = threading.Thread(
            target=self._transcription_worker, daemon=True)
        self._transcription_worker_thread.start()

        self.rec_btn.config(text="■  Avsluta möte", bg=RED, fg="#FFFFFF")
        self.notes_btn.config(state="disabled", bg=BG, fg=FG_DIM)
        self.save_btn.config(state="disabled", bg=BG, fg=FG_DIM)
        self._set_status("● Spelar in  —  Mikrofon")
        self._tick()
        self.rec_thread = threading.Thread(target=self._record_loop, daemon=True)
        self.rec_thread.start()
        self._log(f"Inspelning startad — modell: {self.whisper_size.get()}")

    def _stop_recording(self):
        self.recording = False
        if self.timer_id:
            self.after_cancel(self.timer_id)
            self.timer_id = None
        self.rec_btn.config(text="●  Starta inspelning", bg=FG, fg=BG)
        self._set_rec_btn_enabled(False)
        self._set_status("Mötet avslutat — transkriberar kvarvarande ljud…")
        self._log("Ljud stoppat. Väntar på transkription…")
        threading.Thread(target=self._wait_for_transcription, daemon=True).start()

    def _wait_for_transcription(self):
        if self.rec_thread:
            self.rec_thread.join(timeout=15)
        self.transcription_queue.put(None)
        if self._transcription_worker_thread:
            self._transcription_worker_thread.join(timeout=3600)
        self.after(0, self._on_done)

    def _on_done(self):
        self._set_rec_btn_enabled(True)
        self._set_status("Klart.  Klicka 'Generera anteckningar'.")
        if self.transcript_parts:
            self.notes_btn.config(state="normal", bg=BG, fg=ACCENT)
        self._log("Transkription klar.")

    # ── Audio capture ─────────────────────────────────────────────────────────

    def _record_loop(self):
        import sounddevice as sd
        chunk_frames = SAMPLE_RATE * CHUNK_SECONDS
        mic_buf = []

        def mic_cb(indata, frames, t, status):
            mic_buf.extend(indata[:, 0].tolist())

        try:
            s = sd.InputStream(device=self.mic_device_idx.get(), samplerate=SAMPLE_RATE,
                               channels=CHANNELS, dtype="int16", callback=mic_cb)
            s.start()
            try:
                while self.recording:
                    time.sleep(0.1)
                    if len(mic_buf) >= chunk_frames:
                        data = np.array(mic_buf[:chunk_frames], dtype=np.int16)
                        del mic_buf[:chunk_frames]
                        self.audio_chunks.append(data)
                        self._enqueue_transcription(data, len(self.audio_chunks))
                if len(mic_buf) > SAMPLE_RATE:
                    data = np.array(mic_buf, dtype=np.int16)
                    self.audio_chunks.append(data)
                    self._enqueue_transcription(data, len(self.audio_chunks))
            finally:
                s.stop()
                s.close()
        except Exception as e:
            self._log(f"Ljudfel: {e}")
        self._log("Ljudinspelning avslutad.")

    # ── Transcription queue ───────────────────────────────────────────────────

    def _enqueue_transcription(self, chunk, idx):
        self.pending_transcriptions += 1
        self.transcription_queue.put((chunk, idx))
        self.after(0, self._update_pending_status)

    def _update_pending_status(self):
        if self.pending_transcriptions > 0 and not self.recording:
            n = self.pending_transcriptions
            self._set_status(f"Transkriberar — {n} {'del' if n == 1 else 'delar'} kvar…")

    def _transcription_worker(self):
        while True:
            item = self.transcription_queue.get()
            if item is None:
                break
            chunk, idx = item
            self._transcribe_chunk(chunk, idx)
            self.pending_transcriptions -= 1
            self.after(0, self._update_pending_status)

    # ── Transcription + diarization ───────────────────────────────────────────

    def _transcribe_chunk(self, chunk, idx):
        n_pending = self.pending_transcriptions
        self.after(0, lambda i=idx, p=n_pending: self._set_status(
            f"Transkriberar del {i}  ({p} {'kvar' if p > 1 else 'återstår'})…"))
        self._log(f"Transkriberar del {idx} ({len(chunk)/SAMPLE_RATE:.0f}s)…")
        fname = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                fname = f.name
            with wave.open(fname, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(chunk.tobytes())

            segs, info = self.whisper_model.transcribe(
                fname, language=self.language.get(), task="transcribe",
                beam_size=5, vad_filter=True,
                word_timestamps=bool(self.diarization_pipeline))
            segments = list(segs)

            if self.diarization_pipeline and segments:
                text = self._diarize(fname, segments)
            else:
                text = " ".join(s.text for s in segments).strip()

            if fname and os.path.exists(fname):
                os.unlink(fname)
                fname = None

            if text:
                ts = self._fmt_time(len(self.transcript_parts) * CHUNK_SECONDS)
                self.transcript_parts.append(text)
                line = f"[{ts}]\n{text}\n\n"
                self.after(0, lambda t=line: self._append(self.transcript_box, t, FG3))
                self._log(f"Del {idx} ({info.language}): {text.replace(chr(10),' ')[:80]}…")
            else:
                self._log(f"Del {idx}: tyst.")
        except Exception as e:
            self._log(f"Transkriptionsfel del {idx}: {e}")
        finally:
            if fname and os.path.exists(fname):
                try:
                    os.unlink(fname)
                except Exception:
                    pass

    def _diarize(self, fname, segments):
        try:
            n_speakers = None
            participants_str = self.participants.get().strip()
            if participants_str:
                count = len([p for p in participants_str.split(",") if p.strip()])
                if count >= 2:
                    n_speakers = count
                    self._log(f"Diarisering med {n_speakers} kända talare.")

            diarization_kw = {"num_speakers": n_speakers} if n_speakers else {}
            diarization = self.diarization_pipeline(fname, **diarization_kw)
            turns = sorted(
                [(t.start, t.end, spk)
                 for t, _, spk in diarization.itertracks(yield_label=True)],
                key=lambda x: x[0])

            def find_speaker(t: float) -> str:
                for start, end, spk in turns:
                    if start <= t <= end:
                        return spk
                if turns:
                    return min(turns, key=lambda x: min(abs(x[0]-t), abs(x[1]-t)))[2]
                return "OKÄND"

            word_entries = []
            for seg in segments:
                if hasattr(seg, "words") and seg.words:
                    for w in seg.words:
                        word_entries.append((w.start, w.end, w.word))
                else:
                    word_entries.append((seg.start, seg.end, seg.text.strip()))

            if not word_entries:
                return " ".join(s.text for s in segments).strip()

            labeled = [(find_speaker((s+e)/2), w) for s, e, w in word_entries]

            lines, cur_spk, cur_words = [], None, []
            for spk, word in labeled:
                if spk != cur_spk:
                    if cur_words:
                        lines.append(f"**{cur_spk}:** {''.join(cur_words).strip()}")
                    cur_spk, cur_words = spk, [word]
                else:
                    cur_words.append(word)
            if cur_words:
                lines.append(f"**{cur_spk}:** {''.join(cur_words).strip()}")

            result = "\n".join(lines)
            return result if result.strip() else " ".join(w for _, _, w in word_entries)
        except Exception as e:
            self._log(f"Diariseringsfel: {e}")
            return " ".join(s.text for s in segments).strip()

    # ── Notes generation ──────────────────────────────────────────────────────

    def _generate_notes(self):
        if not self.transcript_parts:
            messagebox.showinfo("Tomt", "Inget transkript.")
            return
        self.notes_btn.config(state="disabled", bg=BG3, fg=FG_DIM, text="Genererar…")
        self._set_status("Genererar mötesanteckningar med Claude…")
        self.active_tab.set("notes")
        self._switch_tab()
        threading.Thread(target=self._call_claude, daemon=True).start()

    def _call_claude(self):
        transcript   = "\n".join(self.transcript_parts)
        title        = self.meeting_title.get().strip() or "Möte"
        participants = self.participants.get().strip()
        date_str     = (self.recording_start_time or datetime.now()).strftime("%Y-%m-%d %H:%M")
        org          = self.user_name or "organisationen"

        system = (
            f"Du är en expert på att skriva strukturerade och handlingsbara mötesanteckningar "
            f"för {org}. Svara alltid på samma språk som transkriptet."
        )
        prompt = (
            f"Analysera transkriptet och generera mötesanteckningar.\n\n"
            f"Möte: {title}\nDatum: {date_str}\n"
            f"{'Deltagare: ' + participants if participants else ''}\n\n"
            f"TRANSKRIPT:\n{transcript}\n\n"
            f"# {title}\n**Datum:** {date_str}\n"
            f"{'**Deltagare:** ' + participants if participants else ''}\n\n"
            f"## Sammanfattning\n## Beslut\n"
            f"## Action Points\n| Åtgärd | Ansvarig | Deadline |\n|--------|----------|----------|\n\n"
            f"## Nästa steg\n## Diskussion i sammandrag\n\n"
            f"---\n*Genererat av {org} · Powered by Liljedahl Legal Tech*"
        )
        try:
            resp = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514", max_tokens=2000,
                system=system, messages=[{"role": "user", "content": prompt}])
            notes = resp.content[0].text
            self.after(0, lambda n=notes: self._show_notes(n))
        except Exception as e:
            self._log(f"Claude API-fel: {e}")
            self.after(0, lambda: messagebox.showerror("API-fel", str(e)))
            self.after(0, lambda: self.notes_btn.config(
                state="normal", bg=BG, fg=ACCENT, text="◆  Generera anteckningar"))

    def _show_notes(self, notes):
        self._clear(self.notes_box)
        self._append(self.notes_box, notes)
        self.notes_btn.config(state="normal", bg=BG, fg=GREEN, text="✓  Klara")
        self.save_btn.config(state="normal", bg=BG, fg=ACCENT)
        self._set_status("Anteckningar klara.  Klicka 'Spara' för att exportera.")
        self._log("Anteckningar genererade.")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save_output(self):
        fmt     = self.save_format.get()
        title   = self.meeting_title.get().strip().replace(" ", "_") or "mote"
        default = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{title}"

        ext_map = {"md": ".md", "docx": ".docx", "pdf": ".pdf"}
        ft_map  = {
            "md":   [("Markdown", "*.md"),   ("Alla", "*.*")],
            "docx": [("Word-dokument", "*.docx"), ("Alla", "*.*")],
            "pdf":  [("PDF", "*.pdf"),        ("Alla", "*.*")],
        }
        path = filedialog.asksaveasfilename(
            defaultextension=ext_map[fmt], initialfile=default,
            filetypes=ft_map[fmt], title="Spara mötesanteckningar")
        if not path:
            return

        org = self.user_name or "Meeting Recorder"
        content_md = (
            f"# {self.meeting_title.get() or 'Möte'}\n"
            f"*{datetime.now().strftime('%Y-%m-%d %H:%M')} · {org} · Powered by Liljedahl Legal Tech*\n\n---\n\n"
            f"{self.notes_box.get('1.0', 'end').strip()}\n\n---\n\n## Fullständigt transkript\n\n"
            + "\n".join(self.transcript_parts) + "\n"
        )
        try:
            if fmt == "md":
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content_md)
            elif fmt == "docx":
                self._save_as_docx(path, content_md)
            elif fmt == "pdf":
                self._save_as_pdf(path, content_md)
            self._set_status(f"Sparat: {path}")
            self._log(f"Fil sparad: {path}")
        except Exception as e:
            messagebox.showerror("Sparfel", str(e))

    def _save_as_docx(self, path, md_text):
        from docx import Document
        from docx.shared import Pt
        doc = Document()
        table_rows = []

        def flush_table():
            if not table_rows:
                return
            data_rows = [r for r in table_rows if not all(
                c.strip().replace("-","").replace(":","") == "" for c in r)]
            if not data_rows:
                table_rows.clear()
                return
            cols = len(data_rows[0])
            t = doc.add_table(rows=len(data_rows), cols=cols)
            t.style = "Table Grid"
            for ri, row in enumerate(data_rows):
                for ci, cell in enumerate(row[:cols]):
                    t.cell(ri, ci).text = cell.strip()
            table_rows.clear()

        for line in md_text.splitlines():
            if line.strip().startswith("|"):
                table_rows.append([c for c in line.strip().strip("|").split("|")])
                continue
            flush_table()
            s = line.strip()
            if s.startswith("### "):   doc.add_heading(s[4:], level=3)
            elif s.startswith("## "): doc.add_heading(s[3:], level=2)
            elif s.startswith("# "):  doc.add_heading(s[2:], level=1)
            elif s == "---":
                p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(6)
            elif s == "":
                doc.add_paragraph()
            else:
                p = doc.add_paragraph()
                for i, part in enumerate(s.split("**")):
                    if not part: continue
                    run = p.add_run(part)
                    if i % 2 == 1: run.bold = True
                    elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                        run.text = part[1:-1]; run.italic = True
        flush_table()
        doc.save(path)

    def _save_as_pdf(self, path, md_text):
        from fpdf import FPDF

        # Margins MUST be set before add_page()
        pdf = FPDF()
        L, R, T = 22, 22, 22
        pdf.set_margins(L, T, R)
        pdf.set_auto_page_break(auto=True, margin=22)
        pdf.add_page()

        # Usable width
        pw = pdf.w - L - R

        def clean(t):
            return t.replace("**", "").replace("*", "").replace("`", "").strip()

        def is_separator_row(s):
            return all(c in "-|: " for c in s)

        def write(font_style, size, line_h, text, extra_ln=0):
            pdf.set_font("Helvetica", font_style, size)
            pdf.set_x(L)
            pdf.multi_cell(pw, line_h, text, align="L")
            if extra_ln:
                pdf.ln(extra_ln)

        def render_table(rows):
            """Render a list of cell-lists as a clean monochrome PDF table."""
            if not rows:
                return
            n_cols = max(len(r) for r in rows)
            if n_cols == 0:
                return
            col_w = pw / n_cols
            row_h = 7
            header = rows[0]
            body   = rows[1:]

            pdf.set_draw_color(180, 180, 180)

            # Header row — bold, underlined by top border
            y_start = pdf.get_y()
            pdf.line(L, y_start, L + pw, y_start)
            for ci, cell in enumerate(header):
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(30, 30, 30)
                pdf.set_xy(L + ci * col_w, pdf.get_y())
                pdf.cell(col_w, row_h, cell.strip(), border=0, align="L")
            pdf.ln(row_h)
            y_line = pdf.get_y()
            pdf.line(L, y_line, L + pw, y_line)

            # Body rows
            for row in body:
                for ci in range(n_cols):
                    cell = row[ci].strip() if ci < len(row) else ""
                    pdf.set_font("Helvetica", "", 9)
                    pdf.set_text_color(50, 50, 50)
                    pdf.set_xy(L + ci * col_w, pdf.get_y())
                    pdf.cell(col_w, row_h, cell, border=0, align="L")
                pdf.ln(row_h)

            # Bottom border
            y = pdf.get_y()
            pdf.line(L, y, L + pw, y)
            pdf.set_text_color(0, 0, 0)
            pdf.set_draw_color(0, 0, 0)
            pdf.ln(3)

        # Collect table rows across consecutive | lines
        table_buf = []
        lines = md_text.splitlines()
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if s.startswith("|"):
                if not is_separator_row(s):
                    table_buf.append([c.strip() for c in s.strip("|").split("|")])
            else:
                if table_buf:
                    render_table(table_buf)
                    table_buf = []
                if not s:
                    pdf.ln(4)
                elif s == "---":
                    pdf.ln(2)
                    y = pdf.get_y()
                    pdf.line(L, y, pdf.w - R, y)
                    pdf.ln(4)
                elif s.startswith("# "):
                    write("B", 16, 10, clean(s[2:]), extra_ln=3)
                elif s.startswith("## "):
                    write("B", 13, 8, clean(s[3:]), extra_ln=2)
                elif s.startswith("### "):
                    write("B", 11, 7, clean(s[4:]), extra_ln=1)
                else:
                    write("", 10, 6, clean(s))
            i += 1

        if table_buf:
            render_table(table_buf)

        pdf.output(path)

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _tick(self):
        if not self.recording: return
        h, r = divmod(self.total_seconds, 3600)
        m, s = divmod(r, 60)
        self.timer_lbl.config(text=f"{h:02d}:{m:02d}:{s:02d}", fg=ACCENT)
        self.total_seconds += 1
        self.timer_id = self.after(1000, self._tick)

    @staticmethod
    def _fmt_time(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


if __name__ == "__main__":
    app = MeetingRecorder()
    app.mainloop()
