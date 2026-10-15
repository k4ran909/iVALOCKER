"""
System-wide hotkeys, so iVALOCKER can be controlled while VALORANT has focus.

Uses the Win32 RegisterHotKey API on its own OS thread: Windows tells us when the key
combination is pressed. Nothing is hooked or injected into the game.

Hotkeys are stored as strings like "F8" or "Ctrl+Alt+L".
"""
import ctypes
import logging
import os

logger = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
MODIFIERS = (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN))
MODIFIER_ALIASES = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift",
                    "win": "Win", "meta": "Win", "super": "Win"}

# Keys that are fine on their own (they don't type anything / aren't used to move in game).
STANDALONE_KEYS = {f"F{i}": 0x6F + i for i in range(1, 25)}
STANDALONE_KEYS.update({f"Numpad{i}": 0x60 + i for i in range(10)})
STANDALONE_KEYS.update({"Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23, "PageUp": 0x21,
                        "PageDown": 0x22, "Pause": 0x13, "ScrollLock": 0x91})

# Keys that need at least one modifier, otherwise they'd be swallowed everywhere (typing, moving...).
MODIFIED_KEYS = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
MODIFIED_KEYS.update({str(d): ord(str(d)) for d in range(10)})
MODIFIED_KEYS.update({"Space": 0x20, "Up": 0x26, "Down": 0x28, "Left": 0x25, "Right": 0x27,
                      "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, ";": 0xBA,
                      "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC})

ACTIONS = {
    "hotkey_arm": "Arm / stop",
    "hotkey_next": "Next favorite agent",
    "hotkey_mode": "Switch instalock / hover",
}

WM_HOTKEY, WM_QUIT = 0x0312, 0x0012


def _key_lookup(name):
    for table in (STANDALONE_KEYS, MODIFIED_KEYS):
        for canonical, vk in table.items():
            if canonical.lower() == name.lower():
                return canonical, vk, table is STANDALONE_KEYS
    return None


def parse(spec):
    """'ctrl+alt+l' -> ('Ctrl+Alt+L', modifiers, virtual key code). Returns None if invalid."""
    if not spec or not isinstance(spec, str):
        return None
    parts = [p.strip() for p in spec.replace(" ", "").split("+")]
    # "Ctrl++" style specs would split into empty parts; we don't support '+' as a key.
    if not parts or any(not p for p in parts):
        return None

    *mod_names, key_name = parts
    mods = set()
    for name in mod_names:
        canonical = MODIFIER_ALIASES.get(name.lower())
        if not canonical or canonical in mods:
            return None
        mods.add(canonical)

    found = _key_lookup(key_name)
    if not found:
        return None
    key, vk, standalone = found
    if not standalone and not mods:
        return None

    flags = 0
    ordered = []
    for name, flag in MODIFIERS:
        if name in mods:
            flags |= flag
            ordered.append(name)
    return "+".join(ordered + [key]), flags, vk


def normalize(spec):
    """Canonical form of a hotkey, or '' if it's empty / invalid."""
    parsed = parse(spec)
    return parsed[0] if parsed else ""


class HotkeyManager:
    """
    Registers hotkeys on a dedicated OS thread and calls `on_action(action)` on the gevent loop
    whenever one is pressed. Only works on Windows; elsewhere it does nothing.
    """

    supported = os.name == "nt"

    def __init__(self, on_action, on_errors=None):
        self.on_action = on_action
        self.on_errors = on_errors or (lambda errors: None)
        self._thread_id = None
        self._done = None

    def apply(self, settings):
        """(Re)register the hotkeys from a settings dict. Returns immediately."""
        if not self.supported:
            return
        self.stop()
        bindings = []
        for action in ACTIONS:
            parsed = parse(settings.get(action))
            if parsed:
                bindings.append((action, parsed))
        if bindings:
            self._start(bindings)

    def stop(self):
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread_id = None
        if self._done is not None:
            # Wait (briefly) for the old thread to unregister, so the same keys can be reused.
            self._done.acquire(timeout=1)
            self._done = None

    # -- internals --------------------------------------------------------------------------------

    def _start(self, bindings):
        import gevent
        from gevent import monkey

        # Real OS primitives: gevent has patched `threading`, but this loop blocks in GetMessage.
        start_new_thread = monkey.get_original("_thread", "start_new_thread")
        allocate_lock = monkey.get_original("_thread", "allocate_lock")

        loop = gevent.get_hub().loop
        ready = allocate_lock()
        ready.acquire()
        done = allocate_lock()
        done.acquire()
        self._done = done

        def fire(action):
            gevent.spawn(self.on_action, action)

        def report(errors):
            gevent.spawn(self.on_errors, errors)

        def run():
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            self._thread_id = kernel32.GetCurrentThreadId()
            ids, errors = {}, []
            try:
                for index, (action, (name, flags, vk)) in enumerate(bindings, start=1):
                    if user32.RegisterHotKey(None, index, flags | MOD_NOREPEAT, vk):
                        ids[index] = action
                        logger.info("Hotkey %s -> %s", name, action)
                    else:
                        errors.append(name)
                ready.release()
                if errors:
                    loop.run_callback_threadsafe(report, errors)

                msg = ctypes.wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    if msg.message == WM_HOTKEY and msg.wParam in ids:
                        loop.run_callback_threadsafe(fire, ids[msg.wParam])
            except Exception:
                logger.exception("Hotkey thread crashed")
            finally:
                for index in ids:
                    user32.UnregisterHotKey(None, index)
                if ready.locked():
                    ready.release()
                done.release()

        import ctypes.wintypes  # noqa: F401  (Windows only)
        start_new_thread(run, ())
        ready.acquire(timeout=2)
