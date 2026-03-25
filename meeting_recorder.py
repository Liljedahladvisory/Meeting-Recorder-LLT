#!/usr/bin/env python3
"""
Duch's Meeting Recorder & Notes Generator — v1
Duch
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, ttk
import threading
import queue
import os
import time
import wave
import tempfile
from datetime import datetime
import numpy as np

SAMPLE_RATE   = 16000
CHANNELS      = 1
CHUNK_SECONDS = 20

BG       = "#0A0A0A"
BG2      = "#111111"
BG3      = "#1A1A1A"
BG4      = "#222222"
BORDER   = "#2A2A2A"
FG       = "#E8E8E8"
FG2      = "#9A9A9A"
FG3      = "#D4D4D4"
FG_DIM   = "#555555"
RED      = "#C0392B"
GREEN    = "#27AE60"
AMBER    = "#D4A017"

FONT_LOGO1    = ("Helvetica Neue", 15, "bold")
FONT_LOGO2    = ("Helvetica Neue", 15)
FONT_POWERED  = ("Helvetica Neue", 9, "italic")
FONT_H     = ("Helvetica Neue", 11, "bold")
FONT_B     = ("Helvetica Neue", 11)
FONT_S     = ("Helvetica Neue", 10)
FONT_M     = ("Menlo", 10)
FONT_MS    = ("Menlo", 9)
FONT_TIMER = ("Menlo", 13)


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


def is_blackhole(name):
    n = name.lower()
    return "blackhole" in n or "black hole" in n


def mix_channels(a, b):
    length = max(len(a), len(b))
    fa = np.pad(a.astype(np.float32), (0, length - len(a)))
    fb = np.pad(b.astype(np.float32), (0, length - len(b)))
    return np.clip((fa + fb) * 0.5, -32768, 32767).astype(np.int16)


def separator(parent, color=BORDER, padx=0, pady=0):
    tk.Frame(parent, bg=color, height=1).pack(fill="x", padx=padx, pady=pady)


def _set_macos_app_name():
    """Set the macOS menu bar name to 'Meeting Recorder'.
    Must be called BEFORE Tk.__init__ — once tkinter initialises the
    macOS NSApplication the bundle name is already locked in."""
    try:
        from Foundation import NSProcessInfo, NSBundle
        # setProcessName_ is the most reliable way to change the menu bar name
        NSProcessInfo.processInfo().setProcessName_("Duch's Meeting Recorder")
        # Also patch the bundle dictionaries as a belt-and-suspenders measure
        bundle = NSBundle.mainBundle()
        for d in filter(None, [bundle.localizedInfoDictionary(),
                                bundle.infoDictionary()]):
            d["CFBundleName"]        = "Duch's Meeting Recorder"
            d["CFBundleDisplayName"] = "Duch's Meeting Recorder"
    except Exception:
        pass  # PyObjC unavailable — menu bar stays as "Python"


class MeetingRecorder(tk.Tk):
    def __init__(self):
        _set_macos_app_name()   # before super().__init__() — timing is critical
        super().__init__()
        self.title("Duch's Meeting Recorder")
        self.configure(bg=BG)
        self.geometry("900x860")
        self.minsize(760, 700)
        self.resizable(True, True)

        self.api_key        = tk.StringVar()
        self.meeting_title  = tk.StringVar()
        self.participants   = tk.StringVar()
        self.source_mode    = tk.StringVar(value="mic")
        self.language       = tk.StringVar(value="sv")
        self.mic_device_idx = tk.IntVar(value=-1)
        self.bh_device_idx  = tk.IntVar(value=-1)
        self.whisper_size   = tk.StringVar(value="medium")

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
        self._devices               = []

        # Transcription queue — decouples audio capture from transcription
        self.transcription_queue         = queue.Queue()
        self.pending_transcriptions      = 0
        self._transcription_worker_thread = None

        self._build_ui()
        self._load_key_from_env()
        self._poll_log()
        self.after(200, self._refresh_devices)
        threading.Thread(target=self._preload_whisper, daemon=True).start()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_config()
        self._build_audio_source()
        self._build_buttons()
        self._build_tabs()
        self._build_status()
        self._on_mode_change()

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG, padx=28, pady=18)
        hdr.pack(fill="x")
        logo_frame = tk.Frame(hdr, bg=BG)
        logo_frame.pack(side="left")
        tk.Label(logo_frame, text="Duch's", font=FONT_LOGO1, bg=BG, fg=FG2).pack(side="left")
        tk.Label(logo_frame, text="  Meeting Recorder", font=FONT_LOGO2, bg=BG, fg=FG3).pack(side="left")
        tk.Label(logo_frame, text="   Powered by Liljedahl Legal Tech", font=FONT_POWERED,
                 bg=BG, fg=FG_DIM).pack(side="left")
        self.timer_lbl = tk.Label(hdr, text="00:00:00", font=FONT_TIMER, bg=BG, fg=FG_DIM)
        self.timer_lbl.pack(side="right")
        separator(self, color=BORDER)

    def _build_config(self):
        outer = tk.Frame(self, bg=BG, padx=28, pady=14)
        outer.pack(fill="x")
        tk.Label(outer, text="KONFIGURATION", font=("Helvetica Neue", 9),
                 bg=BG, fg=FG_DIM).pack(anchor="w", pady=(0, 8))
        card = tk.Frame(outer, bg=BG2, padx=20, pady=16,
                        highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x")

        def field(label, var, show=None, hint=None):
            row = tk.Frame(card, bg=BG2)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, font=FONT_S, bg=BG2, fg=FG2,
                     width=17, anchor="w").pack(side="left")
            kw = dict(textvariable=var, font=FONT_M, bg=BG3, fg=FG,
                      insertbackground=FG, relief="flat", bd=0,
                      highlightthickness=1, highlightbackground=BORDER, highlightcolor=FG2)
            if show:
                kw["show"] = show
            e = tk.Entry(row, **kw)
            e.pack(side="left", fill="x", expand=True, ipady=6)
            if hint:
                tk.Label(row, text=hint, font=("Helvetica Neue", 9),
                         bg=BG2, fg=FG_DIM).pack(side="left", padx=8)
            return e, row

        self._key_entry, r1 = field("API-nyckel", self.api_key, show="•")
        tk.Button(r1, text="visa", font=("Helvetica Neue", 9),
                  bg=BG3, fg=FG_DIM, relief="flat", bd=0, cursor="hand2",
                  padx=8, pady=2, activebackground=BG4, activeforeground=FG,
                  command=lambda: self._key_entry.config(
                      show="" if self._key_entry.cget("show") == "•" else "•")
                  ).pack(side="left", padx=(4, 0))

        field("Möte / titel", self.meeting_title)
        field("Deltagare", self.participants, hint="namn, roll — kommaseparerade")

        # Språkväljare
        lang_row = tk.Frame(card, bg=BG2)
        lang_row.pack(fill="x", pady=5)
        tk.Label(lang_row, text="Språk", font=FONT_S, bg=BG2, fg=FG2,
                 width=17, anchor="w").pack(side="left")
        for val, label in [("sv", "Svenska"), ("en", "English")]:
            tk.Radiobutton(lang_row, text=label, variable=self.language, value=val,
                           font=FONT_S, bg=BG2, fg=FG, selectcolor=BG2,
                           activebackground=BG2, activeforeground=FG3,
                           cursor="hand2").pack(side="left", padx=(0, 16))

        # Whisper-modell
        model_row = tk.Frame(card, bg=BG2)
        model_row.pack(fill="x", pady=5)
        tk.Label(model_row, text="Whisper-modell", font=FONT_S, bg=BG2, fg=FG2,
                 width=17, anchor="w").pack(side="left")
        for val, lbl, hint in [
            ("small",    "Small",    "snabb"),
            ("medium",   "Medium",   "balanserad"),
            ("large-v3", "Large v3", "bäst kvalitet, långsammast"),
        ]:
            col = tk.Frame(model_row, bg=BG2)
            col.pack(side="left", padx=(0, 4))
            tk.Radiobutton(col, text=lbl, variable=self.whisper_size, value=val,
                           font=FONT_S, bg=BG2, fg=FG, selectcolor=BG2,
                           activebackground=BG2, activeforeground=FG3,
                           cursor="hand2").pack(side="left")
            tk.Label(col, text=f"({hint})", font=("Helvetica Neue", 9),
                     bg=BG2, fg=FG_DIM).pack(side="left", padx=(2, 16))

    def _build_audio_source(self):
        outer = tk.Frame(self, bg=BG, padx=28, pady=6)
        outer.pack(fill="x")
        tk.Label(outer, text="LJUDKÄLLA", font=("Helvetica Neue", 9),
                 bg=BG, fg=FG_DIM).pack(anchor="w", pady=(0, 8))
        card = tk.Frame(outer, bg=BG2, padx=20, pady=16,
                        highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x")

        modes_row = tk.Frame(card, bg=BG2)
        modes_row.pack(fill="x", pady=(0, 12))
        for val, label, sub in [
            ("mic",       "Mikrofon",           "Fysiska möten"),
            ("blackhole", "Teams / Google Meet", "Via BlackHole"),
            ("both",      "Båda",               "Mixar mikrofon + systemljud"),
        ]:
            col = tk.Frame(modes_row, bg=BG2)
            col.pack(side="left", padx=(0, 32))
            tk.Radiobutton(col, text=label, variable=self.source_mode, value=val,
                           font=FONT_H, bg=BG2, fg=FG, selectcolor=BG2,
                           activebackground=BG2, activeforeground=FG3,
                           cursor="hand2", command=self._on_mode_change).pack(anchor="w")
            tk.Label(col, text=sub, font=("Helvetica Neue", 9),
                     bg=BG2, fg=FG_DIM).pack(anchor="w", padx=20)

        separator(card, pady=8)

        dev_row = tk.Frame(card, bg=BG2)
        dev_row.pack(fill="x", pady=(4, 0))

        self._mic_frame = tk.Frame(dev_row, bg=BG2)
        self._mic_frame.pack(side="left", fill="x", expand=True, padx=(0, 16))
        tk.Label(self._mic_frame, text="Mikrofon", font=FONT_S,
                 bg=BG2, fg=FG2).pack(anchor="w", pady=(0, 3))
        self._mic_combo = ttk.Combobox(self._mic_frame, state="readonly", font=FONT_MS, width=34)
        self._mic_combo.pack(fill="x")
        self._mic_combo.bind("<<ComboboxSelected>>", self._on_mic_select)

        self._bh_frame = tk.Frame(dev_row, bg=BG2)
        self._bh_frame.pack(side="left", fill="x", expand=True)
        tk.Label(self._bh_frame, text="BlackHole / systemljud", font=FONT_S,
                 bg=BG2, fg=FG2).pack(anchor="w", pady=(0, 3))
        self._bh_combo = ttk.Combobox(self._bh_frame, state="readonly", font=FONT_MS, width=34)
        self._bh_combo.pack(fill="x")
        self._bh_combo.bind("<<ComboboxSelected>>", self._on_bh_select)

        self._bh_banner = tk.Frame(card, bg="#0F0E08", pady=8, padx=12)
        tk.Label(self._bh_banner,
                 text="BlackHole hittades inte.  brew install blackhole-2ch",
                 font=FONT_MS, bg="#0F0E08", fg="#8A7A3A").pack(anchor="w")

        btn_row = tk.Frame(card, bg=BG2)
        btn_row.pack(fill="x", pady=(10, 0))
        tk.Button(btn_row, text="↺  Uppdatera enheter", font=("Helvetica Neue", 9),
                  bg=BG3, fg=FG_DIM, relief="flat", bd=0, cursor="hand2",
                  padx=10, pady=4, activebackground=BG4, activeforeground=FG,
                  command=self._refresh_devices).pack(side="right")

    def _build_buttons(self):
        btn_frame = tk.Frame(self, bg=BG, padx=28, pady=16)
        btn_frame.pack(fill="x")

        # Use Label instead of Button so macOS Aqua theme doesn't override bg colour
        self._rec_btn_enabled = True
        self.rec_btn = tk.Label(btn_frame, text="●  Starta inspelning",
                                font=("Helvetica Neue", 12, "bold"),
                                bg=FG, fg=BG, padx=28, pady=11, cursor="hand2")
        self.rec_btn.bind("<Button-1>", self._on_rec_btn_click)
        self.rec_btn.pack(side="left", padx=(0, 10))

        self.notes_btn = tk.Button(btn_frame, text="◆  Generera anteckningar",
                                   font=("Helvetica Neue", 12),
                                   bg=BG3, fg=FG_DIM, relief="flat", bd=0,
                                   padx=28, pady=11, cursor="hand2",
                                   activebackground=BG4, activeforeground=FG,
                                   state="disabled", command=self._generate_notes)
        self.notes_btn.pack(side="left", padx=(0, 10))

        self.save_btn = tk.Button(btn_frame, text="↓  Spara",
                                  font=("Helvetica Neue", 12),
                                  bg=BG3, fg=FG_DIM, relief="flat", bd=0,
                                  padx=20, pady=11, cursor="hand2",
                                  activebackground=BG4, activeforeground=FG,
                                  state="disabled", command=self._save_output)
        self.save_btn.pack(side="left")
        separator(self, color=BORDER)

    def _build_tabs(self):
        tab_bar = tk.Frame(self, bg=BG, padx=28)
        tab_bar.pack(fill="x")
        self.active_tab = tk.StringVar(value="transcript")
        for label, key in [("Transkript", "transcript"),
                            ("Mötesanteckningar", "notes"),
                            ("Log", "log")]:
            tk.Radiobutton(tab_bar, text=label, variable=self.active_tab, value=key,
                           font=FONT_B, bg=BG, fg=FG_DIM, selectcolor=BG,
                           activebackground=BG, activeforeground=FG,
                           indicatoron=False, relief="flat", bd=0,
                           padx=16, pady=10, cursor="hand2",
                           command=self._switch_tab).pack(side="left")
        separator(self, color=BORDER)

        self.text_frame = tk.Frame(self, bg=BG, padx=28, pady=12)
        self.text_frame.pack(fill="both", expand=True)

        kw = dict(bg=BG2, fg=FG, insertbackground=FG, relief="flat", bd=0,
                  wrap="word", state="disabled", selectbackground=BORDER,
                  highlightthickness=1, highlightbackground=BORDER)
        self.transcript_box = scrolledtext.ScrolledText(self.text_frame, font=FONT_M, **kw)
        self.notes_box = scrolledtext.ScrolledText(self.text_frame, font=FONT_B, **kw)
        self.log_box = scrolledtext.ScrolledText(self.text_frame, font=FONT_MS,
                                                  fg=FG_DIM, **{k: v for k, v in kw.items() if k != "fg"})
        self.transcript_box.pack(fill="both", expand=True)
        self._switch_tab()

    def _build_status(self):
        separator(self, color=BORDER)
        self.status_var = tk.StringVar(value="Redo.")
        status_frame = tk.Frame(self, bg=BG)
        status_frame.pack(fill="x")
        tk.Label(status_frame, textvariable=self.status_var, font=("Helvetica Neue", 10),
                 bg=BG, fg=FG_DIM, anchor="w", padx=28, pady=8).pack(side="left")
        tk.Label(status_frame, text="Powered by Liljedahl Legal Tech",
                 font=FONT_POWERED, bg=BG, fg=FG_DIM, padx=28, pady=8).pack(side="right")

    # ── Device handling ───────────────────────────────────────────────────────

    def _refresh_devices(self):
        self._devices = list_audio_devices()
        if not self._devices:
            self._set_status("sounddevice ej tillgängligt")
            return
        names = [f"{d['name']}  [{d['index']}]" for d in self._devices]
        self._mic_combo["values"] = names
        self._bh_combo["values"]  = names
        bh_pos  = [i for i, d in enumerate(self._devices) if is_blackhole(d["name"])]
        mic_pos = [i for i, d in enumerate(self._devices) if not is_blackhole(d["name"])]
        if bh_pos:
            self._bh_combo.current(bh_pos[0])
            self.bh_device_idx.set(self._devices[bh_pos[0]]["index"])
            self._bh_banner.pack_forget()
        else:
            self._bh_banner.pack(fill="x", pady=(8, 0))
        if mic_pos:
            self._mic_combo.current(mic_pos[0])
            self.mic_device_idx.set(self._devices[mic_pos[0]]["index"])
        self._log(f"{len(self._devices)} enheter. BlackHole: {'hittad' if bh_pos else 'ej hittad'}.")

    def _on_mic_select(self, _=None):
        idx = self._mic_combo.current()
        if idx >= 0: self.mic_device_idx.set(self._devices[idx]["index"])

    def _on_bh_select(self, _=None):
        idx = self._bh_combo.current()
        if idx >= 0: self.bh_device_idx.set(self._devices[idx]["index"])

    def _on_mode_change(self):
        mode = self.source_mode.get()
        self._mic_combo.config(state="readonly" if mode in ("mic", "both") else "disabled")
        self._bh_combo.config(state="readonly" if mode in ("blackhole", "both") else "disabled")

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _switch_tab(self):
        for w in (self.transcript_box, self.notes_box, self.log_box): w.pack_forget()
        {"transcript": self.transcript_box, "notes": self.notes_box,
         "log": self.log_box}[self.active_tab.get()].pack(fill="both", expand=True)

    def _set_status(self, msg): self.status_var.set(msg)
    def _log(self, msg): self.log_q.put(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _poll_log(self):
        while not self.log_q.empty(): self._append(self.log_box, self.log_q.get() + "\n")
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

    def _load_key_from_env(self):
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            self.api_key.set(key)
            self._log("API-nyckel laddad från miljövariabel.")

    # ── Whisper loading ───────────────────────────────────────────────────────

    def _preload_whisper(self):
        size = self.whisper_size.get()
        self.after(0, lambda: self._set_rec_btn_enabled(False))
        try:
            from faster_whisper import WhisperModel
            from pyannote.audio import Pipeline
            self._log(f"Förladdar Whisper {size} i bakgrunden…")
            self.after(0, lambda: self._set_status(f"Laddar Whisper {size}…  (knappen aktiveras när den är klar)"))
            self.whisper_model = WhisperModel(size, device="cpu", compute_type="int8")
            self._loaded_whisper_size = size
            self._log("Whisper redo. Laddar talarseparation…")
            self.after(0, lambda: self._set_status("Laddar talarseparation…"))
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

    def _on_rec_btn_click(self, _=None):
        if self._rec_btn_enabled:
            self._toggle_recording()

    def _set_rec_btn_enabled(self, enabled: bool):
        self._rec_btn_enabled = enabled
        self.rec_btn.config(cursor="hand2" if enabled else "")

    def _toggle_recording(self):
        if not self.recording: self._start_recording()
        else: self._stop_recording()

    def _start_recording(self):
        key = self.api_key.get().strip()
        if not key:
            messagebox.showerror("API-nyckel saknas", "Fyll i Anthropic API-nyckel."); return
        try:
            import anthropic as ac
            self.anthropic_client = ac.Anthropic(api_key=key)
        except Exception as e:
            messagebox.showerror("Fel", str(e)); return
        mode = self.source_mode.get()
        if mode in ("mic", "both") and self.mic_device_idx.get() < 0:
            messagebox.showerror("Ingen mikrofon", "Välj en mikrofonenhet."); return
        if mode in ("blackhole", "both") and self.bh_device_idx.get() < 0:
            messagebox.showerror("BlackHole saknas", "brew install blackhole-2ch"); return
        # Reload Whisper if model size changed or not yet loaded
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
        self.pending_transcriptions = 0
        self._clear(self.transcript_box)
        self._clear(self.notes_box)

        # Fresh transcription queue and worker for this session
        self.transcription_queue = queue.Queue()
        self._transcription_worker_thread = threading.Thread(
            target=self._transcription_worker, daemon=True)
        self._transcription_worker_thread.start()

        mode = self.source_mode.get()
        label = {"mic": "Mikrofon", "blackhole": "Teams/Meet", "both": "Mikrofon + BlackHole"}.get(mode, mode)
        self.rec_btn.config(text="■  Avsluta möte", bg=RED, fg="white")
        self.notes_btn.config(state="disabled", bg=BG3, fg=FG_DIM)
        self.save_btn.config(state="disabled", bg=BG3, fg=FG_DIM)
        self._set_status(f"● Spelar in  —  {label}")
        self._tick()
        self.rec_thread = threading.Thread(target=self._record_loop, args=(mode,), daemon=True)
        self.rec_thread.start()
        self._log(f"Inspelning startad — läge: {mode}, modell: {self.whisper_size.get()}")

    def _stop_recording(self):
        """Stop audio capture immediately. Transcription continues in background."""
        self.recording = False
        if self.timer_id: self.after_cancel(self.timer_id); self.timer_id = None
        self.rec_btn.config(text="●  Starta inspelning", bg=FG, fg=BG)
        self._set_rec_btn_enabled(False)
        self._set_status("Mötet avslutat — transkriberar kvarvarande ljud…")
        self._log("Ljud stoppat. Väntar på att transkription ska slutföras…")
        threading.Thread(target=self._wait_for_transcription, daemon=True).start()

    def _wait_for_transcription(self):
        """Wait for audio capture to finish, then drain the transcription queue."""
        if self.rec_thread:
            self.rec_thread.join(timeout=15)
        # Signal transcription worker to stop after draining the queue
        self.transcription_queue.put(None)
        if self._transcription_worker_thread:
            self._transcription_worker_thread.join(timeout=3600)
        self.after(0, self._on_done)

    def _on_done(self):
        self._set_rec_btn_enabled(True)
        self._set_status("Klart.  Klicka 'Generera anteckningar'.")
        if self.transcript_parts:
            self.notes_btn.config(state="normal", bg=FG, fg=BG)
        self._log("Transkription klar.")

    # ── Audio capture ─────────────────────────────────────────────────────────

    def _record_loop(self, mode):
        import sounddevice as sd
        chunk_frames = SAMPLE_RATE * CHUNK_SECONDS
        mic_buf = []
        bh_buf  = []

        def mic_cb(indata, frames, t, status): mic_buf.extend(indata[:, 0].tolist())
        def bh_cb(indata, frames, t, status):  bh_buf.extend(indata[:, 0].tolist())

        streams = []
        try:
            if mode in ("mic", "both"):
                s = sd.InputStream(device=self.mic_device_idx.get(), samplerate=SAMPLE_RATE,
                                   channels=CHANNELS, dtype="int16", callback=mic_cb)
                s.start(); streams.append(s)
            if mode in ("blackhole", "both"):
                s = sd.InputStream(device=self.bh_device_idx.get(), samplerate=SAMPLE_RATE,
                                   channels=CHANNELS, dtype="int16", callback=bh_cb)
                s.start(); streams.append(s)

            while self.recording:
                time.sleep(0.1)
                mic_ok = len(mic_buf) >= chunk_frames if mode in ("mic", "both") else True
                bh_ok  = len(bh_buf)  >= chunk_frames if mode in ("blackhole", "both") else True
                if mic_ok and bh_ok:
                    chunk = self._build_chunk(mode, mic_buf, bh_buf, chunk_frames)
                    if chunk is not None:
                        self.audio_chunks.append(chunk)
                        self._enqueue_transcription(chunk, len(self.audio_chunks))

            # Enqueue any remaining buffered audio
            remainder = max(len(mic_buf), len(bh_buf))
            if remainder > SAMPLE_RATE:
                chunk = self._build_chunk(mode, mic_buf, bh_buf, remainder)
                if chunk is not None:
                    self.audio_chunks.append(chunk)
                    self._enqueue_transcription(chunk, len(self.audio_chunks))
        finally:
            for s in streams:
                try: s.stop(); s.close()
                except Exception: pass
        self._log("Ljudinspelning avslutad.")

    def _build_chunk(self, mode, mic_buf, bh_buf, n):
        if n <= 0: return None
        if mode == "mic":
            data = np.array(mic_buf[:n], dtype=np.int16); del mic_buf[:n]; return data
        elif mode == "blackhole":
            data = np.array(bh_buf[:n], dtype=np.int16); del bh_buf[:n]; return data
        else:
            m = min(len(mic_buf), n); b = min(len(bh_buf), n)
            ma = np.array(mic_buf[:m], dtype=np.int16); ba = np.array(bh_buf[:b], dtype=np.int16)
            del mic_buf[:m]; del bh_buf[:b]
            return mix_channels(ma, ba)

    # ── Transcription queue ───────────────────────────────────────────────────

    def _enqueue_transcription(self, chunk, idx):
        self.pending_transcriptions += 1
        self.transcription_queue.put((chunk, idx))
        self.after(0, self._update_pending_status)

    def _update_pending_status(self):
        if self.pending_transcriptions > 0 and not self.recording:
            self._set_status(
                f"Transkriberar — {self.pending_transcriptions} "
                f"{'del' if self.pending_transcriptions == 1 else 'delar'} kvar…")

    def _transcription_worker(self):
        """Single worker thread that drains the transcription queue."""
        while True:
            item = self.transcription_queue.get()
            if item is None:  # sentinel: no more chunks
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
                wf.setnchannels(CHANNELS); wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE); wf.writeframes(chunk.tobytes())

            # Always request word timestamps so diarization can align if available
            segs, info = self.whisper_model.transcribe(
                fname, language=self.language.get(), task="transcribe",
                beam_size=5, vad_filter=True,
                word_timestamps=bool(self.diarization_pipeline))

            segments = list(segs)  # materialise generator before file is needed again

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
                preview = text.replace("\n", " ")
                self._log(f"Del {idx} ({info.language}): {preview[:80]}…")
            else:
                self._log(f"Del {idx}: tyst.")
        except Exception as e:
            self._log(f"Transkriptionsfel del {idx}: {e}")
        finally:
            if fname and os.path.exists(fname):
                try: os.unlink(fname)
                except Exception: pass

    def _diarize(self, fname, segments):
        """Word-level speaker alignment: assigns each Whisper word to the pyannote
        speaker turn whose interval covers the word's midpoint.  Falls back to
        closest turn for words that land in a silence gap between turns."""
        try:
            # Pass participant count as a hint so pyannote can constrain the model
            n_speakers = None
            participants_str = self.participants.get().strip()
            if participants_str:
                count = len([p for p in participants_str.split(",") if p.strip()])
                if count >= 2:
                    n_speakers = count
                    self._log(f"Diarisering med {n_speakers} kända talare.")

            diarization_kw = {"num_speakers": n_speakers} if n_speakers else {}
            diarization = self.diarization_pipeline(fname, **diarization_kw)

            # Build a sorted list of (start, end, speaker) for lookup
            turns = sorted(
                [(turn.start, turn.end, speaker)
                 for turn, _, speaker in diarization.itertracks(yield_label=True)],
                key=lambda x: x[0],
            )

            def find_speaker(t: float) -> str:
                """Return the speaker whose turn covers t; fall back to closest."""
                for start, end, spk in turns:
                    if start <= t <= end:
                        return spk
                if turns:
                    return min(turns, key=lambda x: min(abs(x[0] - t), abs(x[1] - t)))[2]
                return "OKÄND"

            # Collect word-level entries — use Whisper word timestamps when available
            word_entries: list[tuple[float, float, str]] = []
            for seg in segments:
                if hasattr(seg, "words") and seg.words:
                    for w in seg.words:
                        word_entries.append((w.start, w.end, w.word))
                else:
                    # No word timestamps: treat whole segment as one unit
                    word_entries.append((seg.start, seg.end, seg.text.strip()))

            if not word_entries:
                return " ".join(s.text for s in segments).strip()

            # Assign speaker to every word by its midpoint
            labeled: list[tuple[str, str]] = [
                (find_speaker((s + e) / 2), w) for s, e, w in word_entries
            ]

            # Group consecutive words that share a speaker
            lines: list[str] = []
            current_speaker: str | None = None
            current_words: list[str] = []
            for speaker, word in labeled:
                if speaker != current_speaker:
                    if current_words:
                        lines.append(f"**{current_speaker}:** {''.join(current_words).strip()}")
                    current_speaker = speaker
                    current_words = [word]
                else:
                    current_words.append(word)
            if current_words:
                lines.append(f"**{current_speaker}:** {''.join(current_words).strip()}")

            result = "\n".join(lines)
            return result if result.strip() else " ".join(w for _, _, w in word_entries)

        except Exception as e:
            self._log(f"Diariseringsfel: {e} — faller tillbaka på vanlig text.")
            return " ".join(s.text for s in segments).strip()

    # ── Notes generation ──────────────────────────────────────────────────────

    def _generate_notes(self):
        if not self.transcript_parts:
            messagebox.showinfo("Tomt", "Inget transkript."); return
        self.notes_btn.config(state="disabled", bg=BG3, fg=FG_DIM, text="Genererar…")
        self._set_status("Genererar mötesanteckningar med Claude…")
        self.active_tab.set("notes"); self._switch_tab()
        threading.Thread(target=self._call_claude, daemon=True).start()

    def _call_claude(self):
        transcript   = "\n".join(self.transcript_parts)
        title        = self.meeting_title.get().strip() or "Möte"
        participants = self.participants.get().strip()
        date_str     = datetime.now().strftime("%Y-%m-%d %H:%M")
        system = ("Du är en expert på att skriva strukturerade och handlingsbara mötesanteckningar "
                  "för Liljedahl Advisory AB. Svara alltid på samma språk som transkriptet.")
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
            f"---\n*Genererat av Duch's Meeting Recorder · Powered by Liljedahl Legal Tech*"
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
                state="normal", bg=FG, fg=BG, text="◆  Generera anteckningar"))

    def _show_notes(self, notes):
        self._clear(self.notes_box)
        self._append(self.notes_box, notes)
        self.notes_btn.config(state="normal", bg=GREEN, fg=FG, text="✓  Klara")
        self.save_btn.config(state="normal", bg=FG, fg=BG)
        self._set_status("Anteckningar klara.  Klicka 'Spara' för att exportera.")
        self._log("Anteckningar genererade.")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save_output(self):
        title   = self.meeting_title.get().strip().replace(" ", "_") or "mote"
        default = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{title}"
        path    = filedialog.asksaveasfilename(
            defaultextension=".md", initialfile=default,
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("Alla", "*.*")],
            title="Spara mötesanteckningar")
        if not path: return
        src_label = {"mic": "Mikrofon", "blackhole": "Teams/Meet (BlackHole)",
                     "both": "Mikrofon + BlackHole"}.get(self.source_mode.get(), "")
        content = (
            f"# Mötesanteckningar — {self.meeting_title.get() or 'Möte'}\n"
            f"*{datetime.now().strftime('%Y-%m-%d %H:%M')} | Källa: {src_label} | Liljedahl Advisory*\n\n---\n\n"
            f"{self.notes_box.get('1.0', 'end').strip()}\n\n---\n\n## Fullständigt transkript\n\n"
            + "\n".join(self.transcript_parts) + "\n"
        )
        try:
            with open(path, "w", encoding="utf-8") as f: f.write(content)
            self._set_status(f"Sparat: {path}")
            self._log(f"Fil sparad: {path}")
        except Exception as e:
            messagebox.showerror("Sparfel", str(e))

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _tick(self):
        if not self.recording: return
        h, r = divmod(self.total_seconds, 3600)
        m, s = divmod(r, 60)
        self.timer_lbl.config(text=f"{h:02d}:{m:02d}:{s:02d}", fg=RED)
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
