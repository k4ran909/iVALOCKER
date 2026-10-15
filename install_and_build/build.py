"""
Build a single-file Windows executable with PyInstaller.

    python install_and_build/build.py

The exe ends up in dist/iVALOCKER_k4ran909.exe
"""
import os
import sys

import eel
import PyInstaller.__main__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "iVALOCKER_k4ran909"

os.chdir(ROOT)

eel_js = os.path.join(os.path.dirname(eel.__file__), "eel.js")
sep = os.pathsep  # ";" on Windows, ":" elsewhere

args = [
    "main.py",
    "--name", NAME,
    "--onefile",
    "--noconsole",
    "--noconfirm",
    "--clean",
    "--icon", os.path.join("web", "favicon.ico"),
    "--add-data", f"{eel_js}{sep}eel",
    "--add-data", f"web{sep}web",
    "--hidden-import", "bottle_websocket",
    "--exclude-module", "tkinter",
] + sys.argv[1:]

print("Running: pyinstaller " + " ".join(args) + "\n")
PyInstaller.__main__.run(args)
print(f"\nDone! Your app is in {os.path.join(ROOT, 'dist')}")
