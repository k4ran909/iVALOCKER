"""
iVALOCKER by k4ran909 - the fastest VALORANT agent instalocker.

Run:        python main.py
Debug log:  python main.py --debug        (writes iVALOCKER.log to %LOCALAPPDATA%\\iVALOCKER)
No window:  python main.py --no-window    (serves the UI and prints the URL, handy for development)
"""
# gevent must patch the standard library before anything imports sockets / ssl, so that network
# calls made by the lock engine never freeze the UI.
from gevent import monkey
monkey.patch_all()

import argparse  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import webbrowser  # noqa: E402

import eel  # noqa: E402

# A --noconsole build has no stdout / stderr; give stray prints somewhere harmless to go.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from ivalocker import APP_NAME, __version__  # noqa: E402
from ivalocker.agents import ROLES, Roster  # noqa: E402
from ivalocker.engine import Engine  # noqa: E402
from ivalocker.hotkeys import ACTIONS as HOTKEY_ACTIONS, HotkeyManager, normalize as normalize_hotkey  # noqa: E402
from ivalocker.paths import data_dir, resource_path  # noqa: E402
from ivalocker.settings import Settings  # noqa: E402

# Socials, don't touch! >:(
LINKS = {
    "instagram": "https://www.instagram.com/k4ran909/",
    "github": "https://github.com/k4ran909/",
    "releases": "https://github.com/k4ran909/iVALOCKER/releases/latest",
}

logger = logging.getLogger(APP_NAME)


def parse_args():
    parser = argparse.ArgumentParser(prog=APP_NAME)
    parser.add_argument("--debug", action="store_true", help="write a detailed log file")
    parser.add_argument("--no-window", action="store_true", help="don't open a window, just serve the UI")
    parser.add_argument("--port", type=int, default=0, help="UI port (default: pick a free one)")
    # PyInstaller / Windows can pass extra arguments; never crash on them.
    args, _ = parser.parse_known_args()
    return args


def setup_logging(debug):
    handlers = [logging.StreamHandler()] if sys.stderr else []
    if debug:
        log_file = os.path.join(data_dir(), f"{APP_NAME}.log")
        handlers.append(logging.FileHandler(log_file, mode="w", encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers or [logging.NullHandler()],
    )
    # These are very chatty at DEBUG level.
    for noisy in ("urllib3", "geventwebsocket"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def show_error(title, message):
    """Native message box on Windows, stderr elsewhere."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # 0x10 = MB_ICONERROR
    except (ImportError, AttributeError, OSError):
        print(f"{title}: {message}", file=sys.stderr)


def acquire_single_instance():
    """
    Make sure only one copy runs. Uses a named mutex on Windows (no port conflicts with other apps).
    Returns the handle (keep a reference for the lifetime of the app) or None if already running.
    """
    if os.name != "nt":
        return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}_k4ran909_single_instance")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def window_size():
    """About 70% of the primary monitor, within sensible bounds."""
    width, height = 1280, 800
    try:
        from screeninfo import get_monitors
        monitors = get_monitors()
        primary = next((m for m in monitors if m.is_primary), monitors[0])
        width = int(min(max(primary.width * 0.7, 1100), 1600))
        height = int(min(max(primary.height * 0.75, 700), 1000))
    except Exception as e:  # screeninfo raises different errors on different platforms
        logger.debug("Could not read monitor size: %s", e)
    return width, height


# ---------------------------------------------------------------------------------------------
# Wiring between the engine and the web UI
# ---------------------------------------------------------------------------------------------

settings = Settings()
roster = Roster()


def emit(kind, payload):
    """Push an event to the UI. Silently ignored while no window is connected."""
    # Without this check Eel queues the calls and replays stale events once a window connects;
    # the window pulls the current state itself with get_bootstrap().
    if not getattr(eel, "_websockets", None):
        return
    try:
        eel.on_event(kind, payload)
    except Exception as e:
        logger.debug("UI event %s dropped: %s", kind, e)


engine = Engine(roster, settings, emit)


def on_hotkey(action):
    """A global hotkey was pressed (usually while the game has focus)."""
    if action == "hotkey_arm":
        state = engine.toggle_arm()
        emit("hotkey", {"action": "arm" if state["armed"] else "disarm", "agent": state["agent"]})
    elif action == "hotkey_next":
        state = engine.cycle_favorite()
        emit("hotkey", {"action": "agent", "agent": state["agent"]})
    elif action == "hotkey_mode":
        mode = engine.toggle_mode()
        emit("settings", settings.as_dict())
        emit("hotkey", {"action": "mode", "mode": mode})


def on_hotkey_errors(keys):
    emit("toast", {"level": "error", "title": "Hotkey unavailable",
                   "text": f"{', '.join(keys)} is already used by another app. Pick a different key."})


hotkeys = HotkeyManager(on_hotkey, on_hotkey_errors)


@eel.expose
def get_bootstrap():
    """Everything the UI needs on startup."""
    return {
        "version": __version__,
        "agents": roster.as_list(),
        "roles": list(ROLES),
        "settings": settings.as_dict(),
        "hotkeys": {"supported": hotkeys.supported, "actions": HOTKEY_ACTIONS},
        "state": engine.snapshot(),
        "logs": engine.logs(),
    }


@eel.expose
def select_agent(name):
    return engine.set_agent(name)


@eel.expose
def arm(name):
    return engine.arm(name)


@eel.expose
def disarm():
    return engine.disarm()


@eel.expose
def update_settings(changes):
    before = settings.as_dict()
    updated = settings.update(changes)
    if any(updated[k] != before[k] for k in HOTKEY_ACTIONS):
        hotkeys.apply(updated)
    return updated


@eel.expose
def check_hotkey(spec):
    """Canonical form of a hotkey, or '' if it can't be used."""
    return normalize_hotkey(spec)


@eel.expose
def reconnect():
    engine.reconnect()


@eel.expose
def open_link(name):
    if name in LINKS:
        webbrowser.open(LINKS[name])


def refresh_roster():
    if roster.refresh_from_api():
        emit("agents", roster.as_list())


# ---------------------------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------------------------

def start_ui(args):
    size = window_size()
    options = {
        "size": size,
        "port": args.port,
        # autoplay: lets the lock / hotkey sounds play while the window is in the background
        "cmdline_args": ["--disable-http-cache", "--autoplay-policy=no-user-gesture-required",
                         f"--window-size={size[0]},{size[1]}"],
    }

    if args.no_window:
        options["port"] = args.port or 8765
        print(f"{APP_NAME} UI: http://localhost:{options['port']}/index.html")
        # Keep running when the browser tab is closed or reloaded.
        eel.start("index.html", mode=None, close_callback=lambda page, sockets: None, **options)
        return

    # Prefer an app window (Chrome, then Edge, which ships with Windows), then any browser.
    modes = ("chrome", "edge", "default") if os.name == "nt" else ("chrome", "default")
    for mode in modes:
        try:
            logger.debug("Starting UI with mode=%s", mode)
            eel.start("index.html", mode=mode, **options)
            return
        except EnvironmentError as e:
            # Eel raises this before the server starts when the browser can't be found.
            if "Can't find" in str(e) and mode != "default":
                logger.debug("%s not available: %s", mode, e)
                continue
            raise


def main():
    args = parse_args()
    setup_logging(args.debug)
    logger.info("%s %s starting", APP_NAME, __version__)

    instance = acquire_single_instance()
    if not instance:
        show_error(f"{APP_NAME} is already running",
                   f"Another copy of {APP_NAME} is already open.\n\n"
                   "Check your taskbar and close it before starting a new one.")
        sys.exit(1)

    eel.init(resource_path("web"))
    engine.start()
    hotkeys.apply(settings.as_dict())
    eel.spawn(refresh_roster)

    try:
        start_ui(args)
    except (SystemExit, KeyboardInterrupt):
        pass
    except Exception as e:
        logger.exception("Failed to start the UI")
        show_error("Startup error", f"{APP_NAME} could not start:\n\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
