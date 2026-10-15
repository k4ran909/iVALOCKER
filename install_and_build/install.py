"""
Install everything needed to run / build iVALOCKER from source.

    python install_and_build/install.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if sys.version_info < (3, 9):
    sys.exit("iVALOCKER needs Python 3.9 or newer.")

if sys.version_info[:3] == (3, 10, 0):
    sys.exit("Python 3.10.0 has a known PyInstaller bug (https://github.com/pyinstaller/pyinstaller/issues/6301). "
             "Please install any other version, e.g. 3.12.")

print(f"Installing dependencies for Python {sys.version.split()[0]}...")
result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "-r", os.path.join(ROOT, "requirements.txt")])
if result.returncode != 0:
    sys.exit("Installing dependencies failed, see the errors above.")

print("\nInstalled! Run the app with:   python main.py")
print("Build the exe with:            python install_and_build/build.py")
