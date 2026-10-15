# Building iVALOCKER

This guide explains how to run iVALOCKER from source and how to build the two Windows files that
end users download:

| File | What it is |
| --- | --- |
| `iVALOCKER_Setup_<version>.exe` | **One-click installer.** Double-click and it installs, adds Start Menu + desktop shortcuts and opens. Uninstall from *Settings > Apps*. |
| `iVALOCKER_k4ran909.exe` | **Portable app.** A single exe, no install, run it from anywhere. |

## Quick reference

| I want to... | Do this (double-click) | Or run this command |
| --- | --- | --- |
| Install what's needed (once) | `install.bat` | `python install_and_build/install.py` |
| Run the app from source | `run.bat` | `python main.py` |
| Build the portable exe | `build.bat` | `python install_and_build/build.py` |
| Build the installer | `build_installer.bat` | `python install_and_build/build.py --installer` |
| Run the tests | | `python -m pytest` |

Everything ends up in the `dist\` folder.

---

## 1. Requirements

- **Windows 10 or 11, 64-bit**
- **Python 3.9 to 3.13** from [python.org](https://www.python.org/downloads/windows/)
  - During setup, tick **"Add python.exe to PATH"**.
  - Avoid **3.10.0** exactly; it has a PyInstaller bug (any other 3.10.x is fine).
  - Check it worked: open *Command Prompt* and run `python --version`.
- That's all. Inno Setup (used for the installer) is downloaded automatically when needed.

## 2. Get the code

Either clone it:

```bat
git clone https://github.com/k4ran909/iVALOCKER.git
cd iVALOCKER
```

or on GitHub click **Code > Download ZIP** and extract it.

## 3. Install the dependencies (once)

Double-click **`install.bat`**, or run:

```bat
python install_and_build/install.py
```

This installs everything from `requirements.txt` (Eel, gevent, PyInstaller, ...).
Run it again after pulling changes that touch `requirements.txt`.

## 4. Run from source

Double-click **`run.bat`**, or:

```bat
python main.py
```

Useful options:

| Option | What it does |
| --- | --- |
| `--debug` | Writes a detailed log to `%LOCALAPPDATA%\iVALOCKER\iVALOCKER.log` |
| `--no-window` | Doesn't open a window; prints a URL you can open in any browser (handy for UI work) |
| `--port 8765` | Use a fixed port for the UI (default: any free port) |

Edits to files in `web\` (HTML / CSS / JS) show up after reloading the window (`F5`).
Edits to Python files need a restart.

## 5. Build the portable exe

Double-click **`build.bat`**, or:

```bat
python install_and_build/build.py
```

Result: **`dist\iVALOCKER_k4ran909.exe`** (about 27 MB). It contains Python, the app and the UI, so it
runs on any 64-bit Windows 10/11 PC without installing anything.

## 6. Build the one-click installer

Double-click **`build_installer.bat`**, or:

```bat
python install_and_build/build.py --installer
```

Result: **`dist\iVALOCKER_Setup_<version>.exe`** (about 26 MB).

What happens:

1. PyInstaller builds the app as a folder, `dist\iVALOCKER\` (starts faster than the single exe).
2. Inno Setup packs that folder into the installer, using `installer\iVALOCKER.iss`.
   - If Inno Setup isn't installed, a portable copy is downloaded once into `build\innosetup\`
     (NuGet package *Tools.InnoSetup*).
   - To use your own Inno Setup, install it from [jrsoftware.org](https://jrsoftware.org/isdl.php),
     or point the `ISCC` environment variable at `ISCC.exe`.

The installer installs per user (no admin prompt) to `%LOCALAPPDATA%\Programs\iVALOCKER` and starts the
app when done. Run it with `/ALLUSERS` to install to Program Files instead, or `/VERYSILENT` for a
fully silent install.

## 7. Change the version number

Edit `__version__` in **`ivalocker/__init__.py`** (for example `"3.3"`). It's shown in the app's
footer and used for the exe's file properties and the installer name (`iVALOCKER_Setup_3.3.exe`).

## 8. Publish a release

**By hand:** on GitHub open **Releases > Draft a new release**, create a tag like `v3.3`, drag in
`dist\iVALOCKER_Setup_3.3.exe` and `dist\iVALOCKER_k4ran909.exe`, and publish.

**Automatically:** `.github/workflows/release.yml` builds and tests both files on GitHub's Windows
machines for every push and pull request. Pushing a version tag also publishes the release:

```bat
git tag v3.3
git push origin v3.3
```

This needs GitHub Actions to be enabled for the repository (*Settings > Actions > General*).

## 9. Run the tests

```bat
pip install -r requirements-dev.txt
python -m pytest
```

The tests don't need VALORANT; they use fake Riot API responses.

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `'python' is not recognized` | Reinstall Python and tick **"Add python.exe to PATH"**, then open a new Command Prompt. |
| `PermissionError` / "file in use" while building | Close iVALOCKER (check Task Manager too) and build again. |
| Antivirus deletes or blocks the exe | A common false positive for PyInstaller apps. Add an exception for the `dist\` folder. |
| "Windows protected your PC" when running the exe | The exe isn't code-signed. Click **More info > Run anyway**. |
| "Inno Setup could not be found or downloaded" | No internet during the build. Install Inno Setup 6 from [jrsoftware.org](https://jrsoftware.org/isdl.php) and build again. |
| The app opens in a normal browser tab | Chrome or Edge wasn't found; the app falls back to the default browser. It still works. |
| A hotkey shows "already used by another app" | Another program registered that key. Pick another one in the *Hotkeys* panel. |
| Something else goes wrong in the app | Start it with `--debug` (or the *iVALOCKER (debug log)* Start Menu shortcut) and check `%LOCALAPPDATA%\iVALOCKER\iVALOCKER.log`. |

## Building on Linux or macOS (advanced)

PyInstaller can't cross-compile, but the Windows build runs fine under [Wine](https://www.winehq.org/)
with the Windows version of Python. Roughly:

```bash
sudo dpkg --add-architecture i386 && sudo apt update
sudo apt install wine wine32:i386 xvfb
# Windows Python (from NuGet, no installer needed)
curl -L -o python.nupkg https://api.nuget.org/v3-flatcontainer/python/3.12.10/python.3.12.10.nupkg
mkdir winpy && cd winpy && unzip -q ../python.nupkg && cd ..
# eel / bottle-websocket only ship as source; build their wheels with your normal Python
pip wheel --no-deps -w wheels eel bottle-websocket
wine winpy/tools/python.exe -m pip install --find-links wheels -r requirements-dev.txt
# build (pipe the output: Wine's console handles break if it's redirected straight to a file)
wine winpy/tools/python.exe install_and_build/build.py | cat
xvfb-run wine winpy/tools/python.exe install_and_build/build.py --installer | cat
```

Always test the result on a real Windows PC before publishing it.
