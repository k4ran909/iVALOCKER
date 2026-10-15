"""
Build iVALOCKER for Windows.

    python install_and_build/build.py              portable single exe -> dist/iVALOCKER_k4ran909.exe
    python install_and_build/build.py --installer  Windows installer   -> dist/iVALOCKER_Setup_<version>.exe

The installer needs Inno Setup 6 (free): https://jrsoftware.org/isdl.php
(or: winget install JRSoftware.InnoSetup)
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTABLE_NAME = "iVALOCKER_k4ran909"
INSTALLED_NAME = "iVALOCKER"
ISS_FILE = os.path.join(ROOT, "installer", "iVALOCKER.iss")
BUILD_DIR = os.path.join(ROOT, "build")


def app_version():
    with open(os.path.join(ROOT, "ivalocker", "__init__.py"), encoding="utf-8") as f:
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
    return match.group(1) if match else "0.0.0"


def numeric_version(version):
    """'3.2' -> (3, 2, 0, 0), as required by Windows version resources."""
    parts = [int(p) for p in re.findall(r"\d+", version)][:4]
    return tuple(parts + [0] * (4 - len(parts)))


def write_version_file(version):
    """Windows file properties (Details tab) for the exe."""
    nums = numeric_version(version)
    dotted = ".".join(map(str, nums))
    path = os.path.join(BUILD_DIR, "version_info.txt")
    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'k4ran909'),
      StringStruct('FileDescription', 'iVALOCKER - VALORANT agent instalocker'),
      StringStruct('FileVersion', '{dotted}'),
      StringStruct('InternalName', 'iVALOCKER'),
      StringStruct('OriginalFilename', 'iVALOCKER.exe'),
      StringStruct('ProductName', 'iVALOCKER'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('LegalCopyright', 'Copyright (c) k4ran909')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""")
    return path


def run_pyinstaller(name, onefile, version):
    import eel
    import PyInstaller.__main__

    eel_js = os.path.join(os.path.dirname(eel.__file__), "eel.js")
    sep = os.pathsep  # ";" on Windows, ":" elsewhere
    args = [
        "main.py",
        "--name", name,
        "--onefile" if onefile else "--onedir",
        "--noconsole",
        "--noconfirm",
        "--clean",
        "--icon", os.path.join("web", "favicon.ico"),
        "--add-data", f"{eel_js}{sep}eel",
        "--add-data", f"web{sep}web",
        "--hidden-import", "bottle_websocket",
        "--exclude-module", "tkinter",
        "--version-file", write_version_file(version),
    ]
    print("Running: pyinstaller " + " ".join(args) + "\n")
    PyInstaller.__main__.run(args)


def find_iscc():
    candidates = [shutil.which("iscc"), shutil.which("ISCC")]
    for base in (os.getenv("ProgramFiles(x86)"), os.getenv("ProgramFiles"),
                 os.path.join(os.getenv("LOCALAPPDATA") or "", "Programs")):
        if base:
            candidates.append(os.path.join(base, "Inno Setup 6", "ISCC.exe"))
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def build_installer(version):
    run_pyinstaller(INSTALLED_NAME, onefile=False, version=version)

    iscc = find_iscc()
    if not iscc:
        sys.exit("\nThe app was built in dist/iVALOCKER, but Inno Setup 6 was not found, so no installer was made.\n"
                 "Install it from https://jrsoftware.org/isdl.php (or: winget install JRSoftware.InnoSetup)\n"
                 "and run this command again.")

    print(f"\nBuilding installer with {iscc}\n")
    result = subprocess.run([iscc, f"/DAppVersion={version}", ISS_FILE])
    if result.returncode != 0:
        sys.exit("Inno Setup failed, see the errors above.")
    print(f"\nDone! Installer: {os.path.join(ROOT, 'dist', f'iVALOCKER_Setup_{version}.exe')}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--installer", action="store_true", help="build the Windows installer instead of the portable exe")
    args = parser.parse_args()

    os.chdir(ROOT)
    version = app_version()
    print(f"Building iVALOCKER {version}\n")

    if args.installer:
        build_installer(version)
    else:
        run_pyinstaller(PORTABLE_NAME, onefile=True, version=version)
        print(f"\nDone! Portable exe: {os.path.join(ROOT, 'dist', PORTABLE_NAME + '.exe')}")


if __name__ == "__main__":
    main()
