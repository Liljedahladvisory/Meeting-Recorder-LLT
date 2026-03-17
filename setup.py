"""
py2app build script for Meeting Recorder.

Usage (one-time setup):
    pip install py2app
    python3 setup.py py2app

The finished app is created at:
    dist/Meeting Recorder.app

After rebuilding, copy or symlink it to /Applications if desired.
"""

from setuptools import setup

APP     = ["meeting_recorder.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName":              "Meeting Recorder",
        "CFBundleDisplayName":       "Meeting Recorder",
        "CFBundleIdentifier":        "se.liljedahladvisory.meeting-recorder",
        "CFBundleVersion":           "1.0",
        "NSHighResolutionCapable":   True,
        "NSMicrophoneUsageDescription":
            "Meeting Recorder behöver åtkomst till mikrofonen för att spela in möten.",
    },
    "packages": ["faster_whisper", "pyannote", "sounddevice", "numpy", "anthropic"],
}

setup(
    name="Meeting Recorder",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
