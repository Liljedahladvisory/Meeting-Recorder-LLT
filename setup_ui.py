#!/usr/bin/env python3
"""
First-run setup UI for Meeting Recorder LLT.
Shows a progress window while installing Python dependencies into ~/.meeting-recorder-llt/venv/

Usage (called by the app launcher):
    python3 setup_ui.py <python_executable> <requirements_path>
"""
import sys
import os
import subprocess
import threading

VENV_DIR = os.path.join(os.path.expanduser("~"), ".meeting-recorder-llt", "venv")

BG      = "#0C0C0E"
BG2     = "#131316"
BG3     = "#1A1A1F"
FG      = "#EDEDF4"
FG2     = "#B8B8D0"
FG_DIM  = "#9090B0"
ACCENT  = "#E8690A"

PACKAGES = [
    ("faster-whisper",  "Whisper (tal-till-text)",           0.40),
    ("pyannote.audio",  "Pyannote (talaridentifiering)",     0.60),
    ("soundfile",       "SoundFile (ljudläsning)",           0.65),
    ("sounddevice",     "Sounddevice (ljudinspelning)",      0.68),
    ("numpy",           "NumPy (beräkningsbibliotek)",       0.74),
    ("anthropic",       "Anthropic (Claude AI)",             0.82),
    ("keyring",         "Keyring (säker nyckellagring)",     0.87),
    ("python-docx",     "Python-docx (Word-export)",        0.93),
    ("fpdf2",           "FPDF2 (PDF-export)",               0.93),
    ("pyobjc-framework-Cocoa", "PyObjC (macOS-integration)",  0.98),
]


def run_setup(python_path: str, requirements_path: str) -> None:
    """Try to show a Tk progress window; fall back to headless if Tk is unavailable."""
    try:
        import tkinter as tk
        _run_with_tk(python_path, tk)
    except Exception:
        _run_headless(python_path)


def _run_with_tk(python_path: str, tk) -> None:
    root = tk.Tk()
    root.title("Meeting Recorder LLT – Förstagångskonfiguration")
    root.configure(bg=BG)
    root.resizable(False, False)

    w, h = 500, 340
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── Header ──────────────────────────────────────────────────────────
    tk.Label(root, text="Meeting Recorder LLT",
             font=("Helvetica Neue", 17, "bold"),
             fg=FG, bg=BG).pack(pady=(30, 3))
    tk.Label(root, text="Powered by Liljedahl Legal Tech",
             font=("Helvetica Neue", 10, "italic"),
             fg=FG_DIM, bg=BG).pack()
    tk.Label(root, text="Installerar beroenden för första gången …",
             font=("Helvetica Neue", 11),
             fg=FG2, bg=BG).pack(pady=(16, 0))

    # ── Status label ────────────────────────────────────────────────────
    status_var = tk.StringVar(value="Förbereder …")
    tk.Label(root, textvariable=status_var,
             font=("Helvetica Neue", 10),
             fg=FG_DIM, bg=BG).pack(pady=(6, 8))

    # ── Progress bar ────────────────────────────────────────────────────
    track = tk.Canvas(root, bg=BG3, height=6, width=420,
                      bd=0, highlightthickness=0)
    track.pack()
    bar_id = track.create_rectangle(0, 0, 0, 6, fill=ACCENT, outline="")

    def set_progress(fraction: float, label: str = "") -> None:
        track.coords(bar_id, 0, 0, 420 * max(0.0, min(1.0, fraction)), 6)
        if label:
            status_var.set(label)
        root.update_idletasks()

    # ── Footer ──────────────────────────────────────────────────────────
    footer_label = tk.Label(root,
             text="Detta sker bara en gång. Stäng inte fönstret.",
             font=("Helvetica Neue", 9, "italic"),
             fg=FG_DIM, bg=BG)
    footer_label.pack(pady=(14, 0))

    # ── Done message (hidden until install finishes) ──────────────────
    done_frame = tk.Frame(root, bg=BG)

    tk.Label(done_frame,
             text="Första gången appen startar kan det ta en extra stund\n"
                  "eftersom AI-modeller laddas ner i bakgrunden.",
             font=("Helvetica Neue", 10),
             fg=FG2, bg=BG, justify="center").pack(pady=(8, 12))

    # Use Frame+Label — tk.Button ignores bg on macOS native rendering
    btn_outer = tk.Frame(done_frame, bg="#E8510A", cursor="hand2")
    btn_outer.pack()
    start_btn = tk.Label(btn_outer, text="  Starta appen  ",
                         font=("Helvetica Neue", 12, "bold"),
                         fg="#FFFFFF", bg="#E8510A",
                         padx=16, pady=8, cursor="hand2")
    start_btn.pack()
    def _on_enter(e): btn_outer.config(bg="#C94208"); start_btn.config(bg="#C94208")
    def _on_leave(e): btn_outer.config(bg="#E8510A"); start_btn.config(bg="#E8510A")
    def _on_click(e): root.destroy()
    for w in (btn_outer, start_btn):
        w.bind("<Enter>", _on_enter)
        w.bind("<Leave>", _on_leave)
        w.bind("<Button-1>", _on_click)

    def _show_done_message():
        footer_label.pack_forget()
        done_frame.pack(pady=(6, 0))

    # ── Worker thread ────────────────────────────────────────────────────
    result = {"error": None}

    def worker() -> None:
        try:
            os.makedirs(os.path.dirname(VENV_DIR), exist_ok=True)

            root.after(0, set_progress, 0.05, "Skapar Python-miljö …")
            subprocess.run(
                [python_path, "-m", "venv", VENV_DIR],
                check=True, capture_output=True,
            )

            pip = os.path.join(VENV_DIR, "bin", "pip")
            root.after(0, set_progress, 0.10, "Uppgraderar pip …")
            subprocess.run(
                [pip, "install", "-q", "--upgrade", "pip"],
                check=True, capture_output=True,
            )

            for pkg, label, prog in PACKAGES:
                root.after(0, set_progress, prog * 0.95,
                           f"Installerar {label} …")
                subprocess.run(
                    [pip, "install", "-q", pkg],
                    check=True, capture_output=True,
                )

            root.after(0, set_progress, 1.0, "Installation klar!")
            root.after(0, _show_done_message)

        except subprocess.CalledProcessError as exc:
            result["error"] = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
            root.after(0, root.destroy)

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()

    if result["error"]:
        raise RuntimeError(result["error"])


def _run_headless(python_path: str) -> None:
    """Silent installation without a GUI (fallback)."""
    os.makedirs(os.path.dirname(VENV_DIR), exist_ok=True)
    subprocess.run([python_path, "-m", "venv", VENV_DIR], check=True)
    pip = os.path.join(VENV_DIR, "bin", "pip")
    subprocess.run([pip, "install", "-q", "--upgrade", "pip"], check=True)
    for pkg, _, _ in PACKAGES:
        subprocess.run([pip, "install", "-q", pkg], check=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: setup_ui.py <python_path> <requirements_path>")
        sys.exit(1)
    run_setup(sys.argv[1], sys.argv[2])
