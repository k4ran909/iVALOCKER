"""
The instalock engine.

A single background greenlet owns the Riot connection and runs forever:

  * not connected  -> try to connect every few seconds (auto-detects VALORANT starting / closing)
  * idle           -> refresh the player's game state about once a second for the UI
  * armed          -> poll the local presence API every few milliseconds; the moment agent select
                      starts, grab the match ID and lock (or hover) the chosen agent

The UI talks to it through arm() / disarm() / set_agent(), and receives updates through `emit`.
"""
import collections
import logging
import time

import gevent
from gevent.event import Event

from .agents import STARTER_AGENTS
from .riot import (ApiError, AuthError, NotRunningError, RiotClient, RiotError, find_player,
                   is_valorant_running, summarize_presence)

logger = logging.getLogger(__name__)

MAP_NAMES = {
    "ascent": "Ascent", "bonsai": "Split", "duality": "Bind", "triad": "Haven", "port": "Icebox",
    "foxtrot": "Breeze", "canyon": "Fracture", "pitt": "Pearl", "jam": "Lotus", "juliett": "Sunset",
    "infinity": "Abyss", "rook": "Corrode", "range": "The Range", "hurm_alley": "District",
    "hurm_yard": "Piazza", "hurm_bowl": "Kasbah", "hurm_helix": "Drift", "hurm_hightide": "Glitch",
}

QUEUE_NAMES = {
    "competitive": "Competitive", "unrated": "Unrated", "swiftplay": "Swiftplay", "spikerush": "Spike Rush",
    "deathmatch": "Deathmatch", "ggteam": "Escalation", "onefa": "Replication", "hurm": "Team Deathmatch",
    "premier": "Premier", "newmap": "New Map", "snowball": "Snowball Fight", "": "Custom",
}

LOG_SIZE = 150
CONNECT_RETRY = 3.0          # seconds between connection attempts
IDLE_INTERVAL = 1.0          # seconds between presence refreshes while not armed
PROCESS_CHECK_INTERVAL = 5.0
MATCH_FOUND_POLL = 0.25      # GLZ poll interval once a match was found (agent select is seconds away)
NO_PRESENCE_POLL = 1.0       # GLZ poll interval when presence is unavailable
PREGAME_RETRY = 0.05         # GLZ poll interval while presence says PREGAME but GLZ has no match yet
MAX_ATTEMPTS_PER_MATCH = 3


def map_name(map_id):
    if not map_id:
        return None
    key = map_id.rstrip("/").split("/")[-1].lower()
    return MAP_NAMES.get(key, map_id.rstrip("/").split("/")[-1])


def queue_name(queue_id):
    if queue_id is None:
        return None
    return QUEUE_NAMES.get(queue_id.lower(), queue_id.replace("_", " ").title())


def game_label(info):
    loop, party = info.get("loop_state"), info.get("party_state")
    if loop == "PREGAME":
        return "Agent select"
    if loop == "INGAME":
        return "In match"
    if party == "MATCHMADE_GAME_STARTING":
        return "Match found"
    if party == "MATCHMAKING":
        return "In queue"
    if loop == "MENUS":
        return "In menus"
    return "Waiting for game"


class Engine:

    def __init__(self, roster, settings, emit=None, client=None):
        self.roster = roster
        self.settings = settings
        self.emit = emit or (lambda *_: None)
        self.client = client or RiotClient()

        self.armed = False
        self.agent = settings["last_agent"] if roster.by_name(settings["last_agent"]) else None
        self.phase = "idle"
        self.detail = ""
        self.connection = {"status": "offline", "message": "Looking for VALORANT...", "player": None, "region": None}
        self.game = {"state": None, "label": "Waiting for game", "queue": None}
        self.result = None
        self.stats = {"locks": 0, "best_ms": None, "last_ms": None}
        self.owned = None

        self._log = collections.deque(maxlen=LOG_SIZE)
        self._wake = Event()
        self._handled = set()
        self._attempts = collections.Counter()
        self._pregame_done = False
        self._last_connect = 0.0
        self._last_process_check = 0.0
        self._last_glz_poll = 0.0
        self._greenlet = None

    # -- public API (called from the UI) -------------------------------------------------------

    def start(self):
        if not self._greenlet:
            self._greenlet = gevent.spawn(self._run)

    def snapshot(self):
        return {
            "armed": self.armed,
            "agent": self.agent,
            "phase": self.phase,
            "detail": self.detail,
            "connection": dict(self.connection),
            "game": dict(self.game),
            "result": dict(self.result) if self.result else None,
            "stats": dict(self.stats),
            "owned": sorted(self.owned) if self.owned is not None else None,
        }

    def logs(self):
        return list(self._log)

    def arm(self, agent_name):
        agent = self.roster.by_name(agent_name)
        if not agent:
            return self._fail_fast(f"Unknown agent: {agent_name}")

        previous = self.agent
        self.agent = agent["name"]
        self.settings.update({"last_agent": self.agent})

        if not self.armed:
            self.armed = True
            self._pregame_done = False
            self._log_add("info", f"Armed: {self.agent}"
                          + (" (hover only)" if self.settings["mode"] == "hover" else ""))
        elif self.agent != previous:
            self._log_add("info", f"Target switched to {self.agent}")

        self._set_phase("armed" if self.client.connected else "waiting")
        self._wake.set()
        return self.snapshot()

    def disarm(self, reason="Stopped"):
        if self.armed:
            self.armed = False
            self._log_add("info", reason)
        if self.phase not in ("locked", "hovered"):
            self._set_phase("idle")
        else:
            self._push_state()
        return self.snapshot()

    def set_agent(self, agent_name):
        """Change the target. Keeps the armed state; arms instead if the user wants arm-on-click."""
        agent = self.roster.by_name(agent_name)
        if not agent:
            return self._fail_fast(f"Unknown agent: {agent_name}")
        if self.armed or self.settings["arm_on_click"]:
            return self.arm(agent["name"])
        self.agent = agent["name"]
        self.settings.update({"last_agent": self.agent})
        if self.phase in ("locked", "hovered", "failed"):
            self.phase = "idle"
        self._push_state()
        return self.snapshot()

    def reconnect(self):
        self.client.connected = False
        self._last_connect = 0
        self._log_add("info", "Reconnecting...")
        self._wake.set()

    # -- main loop ------------------------------------------------------------------------------

    def _run(self):
        while True:
            try:
                delay = self._tick()
            except Exception:  # never let the loop die
                logger.exception("Engine tick failed")
                delay = 1.0
            self._wake.wait(delay)
            self._wake.clear()

    def _tick(self):
        if not self.client.connected:
            if not self._try_connect():
                return 1.0 if self.armed else CONNECT_RETRY

        try:
            if self._game_closed():
                return CONNECT_RETRY
            self.client.ensure_fresh_tokens()
            if self.armed:
                self._armed_tick()
                return self.settings.poll_interval
            self._idle_tick()
            return IDLE_INTERVAL

        except NotRunningError as e:
            self._disconnect(str(e))
            return CONNECT_RETRY
        except AuthError as e:
            self._log_add("warn", f"{e}, reconnecting")
            self.client.connected = False
            return 1.0
        except RiotError as e:
            logger.debug("Transient error: %s", e)
            return 0.5 if self.armed else IDLE_INTERVAL

    def _try_connect(self):
        now = time.monotonic()
        if now - self._last_connect < (1.0 if self.armed else CONNECT_RETRY) and self._last_connect:
            return False
        self._last_connect = now

        if _game_running() is False:
            self._set_connection("offline", "VALORANT is not running")
            return False

        try:
            self.client.connect()
        except NotRunningError as e:
            self._set_connection("offline", str(e))
            return False
        except RiotError as e:
            self._set_connection("error", str(e))
            return False

        self.connection.update({
            "status": "online",
            "message": "Connected",
            "player": self.client.player,
            "region": (self.client.region or "").upper(),
        })
        self._log_add("success", f"Connected to VALORANT as {self.client.player or 'player'} "
                                 f"({(self.client.region or '?').upper()})")
        if self.armed:
            self.phase = "armed"
        self._push_state()
        gevent.spawn(self.client.warm_up)
        gevent.spawn(self._load_owned_agents)
        return True

    def _disconnect(self, message):
        was_online = self.client.connected or self.connection["status"] == "online"
        self.client.connected = False
        self.game = {"state": None, "label": "Waiting for game", "queue": None}
        self.owned = None
        self._set_connection("offline", message)
        if was_online:
            self._log_add("warn", f"Disconnected: {message}")
        if self.armed:
            self._set_phase("waiting")

    def _game_closed(self):
        now = time.monotonic()
        if self.armed or now - self._last_process_check < PROCESS_CHECK_INTERVAL:
            return False
        self._last_process_check = now
        if _game_running() is False:
            self._disconnect("VALORANT was closed")
            return True
        return False

    def _load_owned_agents(self):
        try:
            owned = self.client.owned_agents() | STARTER_AGENTS
        except RiotError as e:
            logger.info("Could not load owned agents: %s", e)
            return
        self.owned = owned
        self._push_state()

    def _idle_tick(self):
        info = summarize_presence(self.client.fetch_presence())
        self._update_game(info)

    def _armed_tick(self):
        presence = self.client.fetch_presence()
        info = summarize_presence(presence)
        self._update_game(info)

        loop, party = info["loop_state"], info["party_state"]
        if loop != "PREGAME":
            self._pregame_done = False
            match_found = party == "MATCHMADE_GAME_STARTING"
            if self.phase in ("locked", "hovered", "failed", "locking") or \
                    (self.phase == "match_found" and not match_found):
                # Agent select is over (or the match was dodged): wait for the next one.
                self._set_phase("armed")

        now = time.monotonic()
        if loop == "PREGAME":
            if self._pregame_done:
                return
            interval = PREGAME_RETRY
        elif party == "MATCHMADE_GAME_STARTING":
            interval = MATCH_FOUND_POLL
            if self.phase == "armed":
                self._set_phase("match_found")
        elif presence is None:
            interval = NO_PRESENCE_POLL
        else:
            return

        if now - self._last_glz_poll < interval:
            return
        self._last_glz_poll = now

        match_id = self.client.pregame_match_id()
        if not match_id:
            return
        if match_id in self._handled:
            self._pregame_done = True
            return
        self._handle_pregame(match_id, info)

    # -- locking --------------------------------------------------------------------------------

    def _handle_pregame(self, match_id, info):
        detected = time.perf_counter()
        hover = self.settings["mode"] == "hover"
        self._set_phase("locking", "Agent select detected")

        delay = self.settings["lock_delay_ms"] / 1000
        if delay:
            gevent.sleep(delay)
            if not self.armed:
                return

        candidates = [self.roster.by_name(self.agent)]
        backup = self.roster.by_name(self.settings["backup_agent"])
        if backup and backup["name"] != self.agent:
            candidates.append(backup)

        errors = []
        for agent in filter(None, candidates):
            started = time.perf_counter()
            try:
                match = self._pick(match_id, agent["uuid"], hover)
            except AuthError:
                raise
            except RiotError as e:
                errors.append(f"{agent['name']}: {_describe(e)}")
                continue

            elapsed_ms = round((time.perf_counter() - started) * 1000)
            total_ms = round((time.perf_counter() - detected) * 1000)
            self._on_success(match_id, agent, match, info, hover, elapsed_ms, total_ms, agent is not candidates[0])
            return

        self._attempts[match_id] += 1
        if self._attempts[match_id] < MAX_ATTEMPTS_PER_MATCH and not any("409" in e or "taken" in e for e in errors):
            self._log_add("warn", f"Attempt failed ({'; '.join(errors)}), retrying")
            return

        self._handled.add(match_id)
        self._pregame_done = True
        message = "; ".join(errors) or "Unknown error"
        self._log_add("error", f"Could not {'select' if hover else 'lock'}: {message}")
        self._set_phase("failed", message)
        self.emit("toast", {"level": "error", "title": "Lock failed", "text": message})
        if not self.settings["keep_armed"]:
            self.armed = False
            self._push_state()

    def _pick(self, match_id, agent_uuid, hover):
        if hover:
            return self.client.select_agent(match_id, agent_uuid)
        try:
            match = self.client.lock_agent(match_id, agent_uuid)
        except ApiError as e:
            if e.status in (404, 409):  # agent select over / agent taken: selecting won't help
                raise
            # Some states require the agent to be selected before it can be locked.
            self.client.select_agent(match_id, agent_uuid)
            match = self.client.lock_agent(match_id, agent_uuid)

        player = find_player(match, self.client.puuid)
        if player and player.get("CharacterSelectionState") not in ("locked", None):
            raise RiotError(f"server reports '{player.get('CharacterSelectionState') or 'not locked'}'")
        return match

    def _on_success(self, match_id, agent, match, info, hover, elapsed_ms, total_ms, used_backup):
        self._handled.add(match_id)
        self._pregame_done = True

        self.result = {
            "agent": agent["name"],
            "ms": elapsed_ms,
            "total_ms": total_ms,
            "hover": hover,
            "backup": used_backup,
            "map": map_name((match or {}).get("MapID")),
            "queue": queue_name((match or {}).get("QueueID") or info.get("queue")),
            "at": int(time.time() * 1000),
        }
        if not hover:
            self.stats["locks"] += 1
            self.stats["last_ms"] = elapsed_ms
            if self.stats["best_ms"] is None or elapsed_ms < self.stats["best_ms"]:
                self.stats["best_ms"] = elapsed_ms

        where = " on " + self.result["map"] if self.result["map"] else ""
        verb = "Hovered" if hover else "Locked"
        self._log_add("success", f"{verb} {agent['name']}{where} in {elapsed_ms} ms"
                                 + (" (backup pick)" if used_backup else ""))

        if not self.settings["keep_armed"]:
            self.armed = False
        self._set_phase("hovered" if hover else "locked")
        self.emit("locked", self.result)

    # -- state helpers --------------------------------------------------------------------------

    def _update_game(self, info):
        game = {"state": info.get("loop_state"), "label": game_label(info), "queue": queue_name(info.get("queue"))}
        if game != self.game:
            if game["state"] == "PREGAME" and self.game.get("state") != "PREGAME" and not self._pregame_done:
                self._log_add("info", "Agent select started")
            elif game["label"] == "Match found" and self.game.get("label") != "Match found":
                self._log_add("info", "Match found")
            self.game = game
            self._push_state()

    def _set_connection(self, status, message):
        if self.connection.get("status") == status and self.connection.get("message") == message:
            return
        self.connection.update({"status": status, "message": message})
        if status != "online":
            self.connection.update({"player": None, "region": None})
        self._push_state()

    def _set_phase(self, phase, detail=""):
        self.phase = phase
        self.detail = detail
        self._push_state()

    def _push_state(self):
        self.emit("state", self.snapshot())

    def _log_add(self, level, text):
        entry = {"t": int(time.time() * 1000), "level": level, "text": text}
        self._log.append(entry)
        log_level = {"error": logging.ERROR, "warn": logging.WARNING}.get(level, logging.INFO)
        logger.log(log_level, text)
        self.emit("log", entry)

    def _fail_fast(self, message):
        self._log_add("error", message)
        self.emit("toast", {"level": "error", "title": "Error", "text": message})
        return self.snapshot()


def _game_running():
    """Process scan in a worker thread so it never stalls the event loop."""
    try:
        return gevent.get_hub().threadpool.apply(is_valorant_running)
    except Exception:
        return None


def _describe(error):
    if isinstance(error, ApiError):
        if error.status == 409:
            return "agent already taken (409)"
        if error.status == 404:
            return "agent select is over (404)"
        return f"HTTP {error.status}{' ' + error.code if error.code else ''}"
    return str(error)
