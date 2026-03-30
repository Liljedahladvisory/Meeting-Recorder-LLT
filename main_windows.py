"""
Meeting Recorder LLT — Windows entry point for PyInstaller.

Checks for a Python-only update at:
  %USERPROFILE%\.meeting-recorder-llt\meeting_recorder.py

If found, runs that instead of the bundled version.
This enables hot-updates without reinstalling the full .exe.
"""
import os
import sys
import runpy

UPDATE_SCRIPT = os.path.join(
    os.path.expanduser("~"), ".meeting-recorder-llt", "meeting_recorder.py"
)

# If bundled by PyInstaller, the bundled script is next to this file
BUNDLED_SCRIPT = os.path.join(
    getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))),
    "meeting_recorder.py",
)

def main():
    if os.path.isfile(UPDATE_SCRIPT):
        script = UPDATE_SCRIPT
    elif os.path.isfile(BUNDLED_SCRIPT):
        script = BUNDLED_SCRIPT
    else:
        import tkinter.messagebox as mb
        mb.showerror(
            "Meeting Recorder LLT",
            "Could not find meeting_recorder.py.\nPlease reinstall the app.",
        )
        sys.exit(1)

    # Run the chosen script as __main__
    sys.argv = [script]
    runpy.run_path(script, run_name="__main__")

if __name__ == "__main__":
    main()
