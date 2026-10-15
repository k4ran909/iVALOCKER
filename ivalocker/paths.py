"""
Filesystem locations used by the app.
"""
import os
import sys

from . import APP_NAME


def resource_path(*parts):
    """
    Path to a file bundled with the app. Works both from source and from a PyInstaller build,
    where bundled data is unpacked to sys._MEIPASS.
    """
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def local_appdata():
    """%LOCALAPPDATA% on Windows, a sensible fallback elsewhere (used for development)."""
    return os.getenv("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")


def data_dir():
    """Per-user folder for settings, caches and logs. Created on first use."""
    path = os.path.join(local_appdata(), APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def riot_lockfile():
    return os.path.join(local_appdata(), "Riot Games", "Riot Client", "Config", "lockfile")


def shooter_game_log():
    return os.path.join(local_appdata(), "VALORANT", "Saved", "Logs", "ShooterGame.log")
