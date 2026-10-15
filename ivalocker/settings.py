"""
User preferences, persisted as JSON in the user's data folder.
"""
import json
import logging
import os

from .hotkeys import normalize as normalize_hotkey
from .paths import data_dir

logger = logging.getLogger(__name__)

# Polling interval (seconds) for each speed profile while armed.
POLL_PROFILES = {
    "turbo": 0.01,
    "fast": 0.05,
    "balanced": 0.15,
}

DEFAULTS = {
    "mode": "lock",            # "lock" = instalock, "hover" = only select (hover) the agent
    "lock_delay_ms": 0,        # optional wait after agent select appears, before locking
    "poll": "turbo",           # key of POLL_PROFILES
    "keep_armed": False,       # stay armed for following matches after a successful lock
    "arm_on_click": True,      # clicking an agent immediately arms the locker
    "backup_agent": None,      # agent to try if the main pick is unavailable
    "sound": True,             # play a sound when an agent gets locked
    "favorites": [],
    "last_agent": None,
    # Global hotkeys (work while the game has focus). "" = disabled.
    "hotkey_arm": "F8",
    "hotkey_next": "F9",
    "hotkey_mode": "",
}


def _coerce(key, value):
    """Validate a single setting, returning a safe value (falls back to the default)."""
    default = DEFAULTS[key]
    try:
        if key == "mode":
            return value if value in ("lock", "hover") else default
        if key == "poll":
            return value if value in POLL_PROFILES else default
        if key == "lock_delay_ms":
            return max(0, min(5000, int(value)))
        if key in ("keep_armed", "arm_on_click", "sound"):
            return bool(value)
        if key in ("backup_agent", "last_agent"):
            return str(value) if value else None
        if key.startswith("hotkey_"):
            return normalize_hotkey(value) if value else ""
        if key == "favorites":
            return [str(v) for v in value][:64] if isinstance(value, list) else default
    except (TypeError, ValueError):
        pass
    return default


class Settings:

    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "settings.json")
        self._values = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for key, value in stored.items():
                    if key in DEFAULTS:
                        self._values[key] = _coerce(key, value)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            logger.warning("Could not read settings, using defaults: %s", e)

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._values, f, indent=2)
            os.replace(tmp, self.path)
        except OSError as e:
            logger.warning("Could not save settings: %s", e)

    def update(self, changes):
        """Apply a dict of changes (unknown keys are ignored) and persist. Returns all settings."""
        for key, value in (changes or {}).items():
            if key in DEFAULTS:
                self._values[key] = _coerce(key, value)
        self.save()
        return self.as_dict()

    def __getitem__(self, key):
        return self._values[key]

    def as_dict(self):
        return dict(self._values, favorites=list(self._values["favorites"]))

    @property
    def poll_interval(self):
        return POLL_PROFILES[self._values["poll"]]
