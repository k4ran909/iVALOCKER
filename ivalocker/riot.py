"""
Minimal client for the two APIs iVALOCKER needs:

  * the local Riot Client API (https://127.0.0.1:<port>, credentials from the lockfile) for
    auth tokens, the player's name and their presence (which tells us when agent select starts)
  * VALORANT's GLZ "pregame" API for finding the agent select match and selecting / locking

Everything goes through persistent requests.Session objects so connections stay warm:
the TLS handshake to the GLZ server happens once, not on every lock attempt.
"""
import base64
import json
import logging
import os
import re
import time

import requests
import urllib3

from .paths import riot_lockfile, shooter_game_log

logger = logging.getLogger(__name__)

# The local Riot Client API uses a self-signed certificate.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REGIONS = ("na", "eu", "latam", "br", "ap", "kr", "pbe")
REGION_TO_SHARD = {"latam": "na", "br": "na", "pbe": "pbe"}

AGENT_ENTITLEMENT_TYPE = "01bb38e1-da47-4e6a-9b3d-945fe4655707"

# Base64 encoded JSON describing the client platform, required by the GLZ / PD servers.
CLIENT_PLATFORM = base64.b64encode(json.dumps({
    "platformType": "PC",
    "platformOS": "Windows",
    "platformOSVersion": "10.0.19042.1.256.64bit",
    "platformChipset": "Unknown",
}).encode()).decode()

# Access tokens live for about an hour, refresh well before that.
TOKEN_MAX_AGE = 40 * 60

LOCAL_TIMEOUT = 2
REMOTE_TIMEOUT = 6


class RiotError(Exception):
    """Base error for everything that can go wrong talking to Riot."""


class NotRunningError(RiotError):
    """The Riot Client / VALORANT is not running (or not logged in yet)."""


class AuthError(RiotError):
    """Our access token was rejected."""


class ApiError(RiotError):

    def __init__(self, status, body=None, message=None):
        self.status = status
        self.body = body if isinstance(body, dict) else {}
        self.code = self.body.get("errorCode") or ""
        super().__init__(message or f"HTTP {status} {self.code}".strip())


# ---------------------------------------------------------------------------------------------
# Parsing helpers (pure functions, easy to test)
# ---------------------------------------------------------------------------------------------

_GLZ_RE = re.compile(rb"https://glz-([a-z]+)-1\.([a-z]+)\.a\.pvp\.net")
_REGIONS_RE = re.compile(rb"regions/([a-z]+)\]")
_CONFIG_RE = re.compile(rb"config/([a-z]+)\]")
_VERSION_RE = re.compile(rb"CI server version: (release-[\w.\-]+)")


def parse_lockfile(text):
    """lockfile format: name:pid:port:password:protocol"""
    parts = text.strip().split(":")
    if len(parts) < 5:
        raise NotRunningError("Riot Client lockfile is malformed")
    return {"name": parts[0], "pid": parts[1], "port": int(parts[2]), "password": parts[3], "protocol": parts[4]}


def parse_region(log_bytes):
    """
    Work out (region, shard) from ShooterGame.log. The most recent GLZ URL in the log is the most
    reliable source; older log formats only contain "regions/xx]" or "config/xx]" fragments.
    Returns (None, None) when nothing was found.
    """
    matches = _GLZ_RE.findall(log_bytes)
    if matches:
        region, shard = (m.decode() for m in matches[-1])
        return region, shard

    for pattern in (_REGIONS_RE, _CONFIG_RE):
        matches = pattern.findall(log_bytes)
        if matches:
            region = matches[-1].decode()
            if region in REGIONS:
                return region, REGION_TO_SHARD.get(region, region)

    return None, None


def parse_client_version(log_bytes):
    matches = _VERSION_RE.findall(log_bytes)
    return matches[-1].decode() if matches else None


def decode_presence(private):
    """Decode the base64 'private' blob of a presence. Returns a dict or None."""
    if not private:
        return None
    try:
        data = json.loads(base64.b64decode(private))
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def summarize_presence(presence):
    """
    Pull the bits we care about out of a VALORANT presence. Handles both the current format
    (nested matchPresenceData / partyPresenceData) and the older flat one.
    """
    if not presence:
        return {"loop_state": None, "party_state": None, "queue": None}

    match = presence.get("matchPresenceData") or {}
    party = presence.get("partyPresenceData") or {}

    return {
        "loop_state": match.get("sessionLoopState") or presence.get("sessionLoopState"),
        "party_state": party.get("partyState") or presence.get("partyState"),
        "queue": match.get("queueId") or presence.get("queueId"),
    }


def find_player(match, puuid):
    """Find our own player entry in a pregame match payload."""
    if not isinstance(match, dict):
        return None
    teams = []
    if isinstance(match.get("AllyTeam"), dict):
        teams.append(match["AllyTeam"])
    teams.extend(t for t in (match.get("Teams") or []) if isinstance(t, dict))
    for team in teams:
        for player in team.get("Players") or []:
            if player.get("Subject") == puuid:
                return player
    return None


# ---------------------------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------------------------

class RiotClient:

    def __init__(self, lockfile_path=None, log_path=None):
        self.lockfile_path = lockfile_path or riot_lockfile()
        self.log_path = log_path or shooter_game_log()

        self.local = requests.Session()
        self.local.verify = False
        self.local.trust_env = False  # never send 127.0.0.1 traffic through a system proxy
        self.remote = requests.Session()

        self.port = None
        self.puuid = None
        self.region = None
        self.shard = None
        self.version = None
        self.game_name = None
        self.game_tag = None
        self.token_time = 0
        self.connected = False

    # -- connection -------------------------------------------------------------------------

    @property
    def glz_url(self):
        return f"https://glz-{self.region}-1.{self.shard}.a.pvp.net"

    @property
    def pd_url(self):
        return f"https://pd.{self.shard}.a.pvp.net"

    @property
    def player(self):
        if self.game_name:
            return f"{self.game_name}#{self.game_tag}" if self.game_tag else self.game_name
        return None

    def connect(self):
        """
        Read the lockfile, get tokens and detect region + client version.
        Raises NotRunningError / RiotError with a human readable message on failure.
        """
        self.connected = False

        try:
            with open(self.lockfile_path, encoding="utf-8") as f:
                lock = parse_lockfile(f.read())
        except FileNotFoundError:
            raise NotRunningError("Riot Client is not running")
        except (OSError, ValueError) as e:
            raise NotRunningError(f"Could not read Riot Client lockfile ({e})")

        self.port = lock["port"]
        self.local.auth = ("riot", lock["password"])
        self.local.headers.clear()

        self.refresh_tokens()

        try:
            with open(self.log_path, "rb") as f:
                log = f.read()
        except OSError:
            raise NotRunningError("VALORANT log not found. Start VALORANT and log in")

        region, shard = parse_region(log)
        if not region:
            region, shard = self._region_from_session()
        if not region:
            raise NotRunningError("Could not detect your region yet. Wait for the main menu")
        self.region, self.shard = region, shard

        self.version = parse_client_version(log) or self._version_from_api()
        if not self.version:
            raise RiotError("Could not detect the VALORANT client version")
        self.remote.headers["X-Riot-ClientVersion"] = self.version
        self.remote.headers["X-Riot-ClientPlatform"] = CLIENT_PLATFORM

        self._fetch_player_name()
        self.connected = True
        logger.info("Connected as %s (%s/%s, %s)", self.player, self.region, self.shard, self.version)

    def refresh_tokens(self):
        data = self._local_get("/entitlements/v1/token")
        if not data.get("accessToken") or not data.get("subject"):
            raise NotRunningError("Not logged in to the Riot Client yet")
        self.puuid = data["subject"]
        self.remote.headers["Authorization"] = f"Bearer {data['accessToken']}"
        self.remote.headers["X-Riot-Entitlements-JWT"] = data.get("token", "")
        self.token_time = time.monotonic()

    def ensure_fresh_tokens(self):
        if time.monotonic() - self.token_time > TOKEN_MAX_AGE:
            logger.debug("Refreshing access token")
            self.refresh_tokens()

    def warm_up(self):
        """Open the TLS connection to the GLZ server ahead of time so the lock request is instant."""
        try:
            self.remote.head(self.glz_url, timeout=REMOTE_TIMEOUT)
        except requests.RequestException:
            pass

    def _region_from_session(self):
        """Fallback: read the deployment from VALORANT's launch arguments."""
        try:
            sessions = self._local_get("/product-session/v1/external-sessions")
        except RiotError:
            return None, None
        for session in sessions.values() if isinstance(sessions, dict) else []:
            args = (session.get("launchConfiguration") or {}).get("arguments") or []
            for arg in args:
                if arg.startswith("-ares-deployment="):
                    region = arg.split("=", 1)[1].lower()
                    if region in REGIONS:
                        return region, REGION_TO_SHARD.get(region, region)
        return None, None

    def _version_from_api(self):
        try:
            r = self.remote.get("https://valorant-api.com/v1/version", timeout=REMOTE_TIMEOUT)
            return r.json()["data"]["riotClientVersion"]
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return None

    def _fetch_player_name(self):
        try:
            session = self._local_get("/chat/v1/session")
            self.game_name = session.get("game_name") or None
            self.game_tag = session.get("game_tag") or None
        except RiotError:
            self.game_name = self.game_tag = None

    # -- local API ----------------------------------------------------------------------------

    def _local_get(self, path):
        if not self.port:
            raise NotRunningError("Riot Client is not running")
        try:
            r = self.local.get(f"https://127.0.0.1:{self.port}{path}", timeout=LOCAL_TIMEOUT)
        except requests.RequestException:
            self.connected = False
            raise NotRunningError("Lost connection to the Riot Client")
        if r.status_code in (401, 403):
            raise NotRunningError("Riot Client rejected the local credentials")
        if r.status_code >= 400:
            raise ApiError(r.status_code, _json(r))
        data = _json(r)
        if data is None:
            raise RiotError(f"Unexpected response from {path}")
        return data

    def fetch_presence(self):
        """Our own decoded VALORANT presence, or None if it isn't available."""
        data = self._local_get("/chat/v4/presences")
        for presence in data.get("presences") or []:
            if presence.get("puuid") == self.puuid and presence.get("product", "valorant") == "valorant":
                return decode_presence(presence.get("private"))
        return None

    # -- remote (GLZ / PD) API -----------------------------------------------------------------

    def _remote(self, method, url, retry=True):
        try:
            r = self.remote.request(method, url, timeout=REMOTE_TIMEOUT)
        except requests.RequestException as e:
            raise RiotError(f"Network error: {e.__class__.__name__}")

        body = _json(r)
        if r.status_code in (400, 401) and _is_auth_problem(body) and retry:
            # Token expired, grab a new one and try once more.
            self.refresh_tokens()
            return self._remote(method, url, retry=False)
        if r.status_code >= 400:
            if r.status_code in (400, 401) and _is_auth_problem(body):
                raise AuthError("Riot rejected the access token")
            raise ApiError(r.status_code, body)
        return body if body is not None else {}

    def pregame_match_id(self):
        """The current agent select match ID, or None when not in agent select."""
        try:
            data = self._remote("GET", f"{self.glz_url}/pregame/v1/players/{self.puuid}")
        except ApiError as e:
            if e.status == 404:
                return None
            raise
        return data.get("MatchID") or None

    def pregame_match(self, match_id):
        return self._remote("GET", f"{self.glz_url}/pregame/v1/matches/{match_id}")

    def select_agent(self, match_id, agent_uuid):
        return self._remote("POST", f"{self.glz_url}/pregame/v1/matches/{match_id}/select/{agent_uuid}")

    def lock_agent(self, match_id, agent_uuid):
        return self._remote("POST", f"{self.glz_url}/pregame/v1/matches/{match_id}/lock/{agent_uuid}")

    def owned_agents(self):
        """UUIDs of agents unlocked on the account (does not include the free starter agents)."""
        data = self._remote("GET", f"{self.pd_url}/store/v1/entitlements/{self.puuid}/{AGENT_ENTITLEMENT_TYPE}")
        return {e.get("ItemID", "").lower() for e in data.get("Entitlements") or [] if e.get("ItemID")}


def _json(response):
    try:
        return response.json()
    except ValueError:
        return None


def _is_auth_problem(body):
    code = (body or {}).get("errorCode", "") if isinstance(body, dict) else ""
    return code in ("BAD_CLAIMS", "UNAUTHORIZED", "TOKEN_EXPIRED", "INVALID_TOKEN") or "token" in code.lower()


def is_valorant_running():
    """Cheap-ish check for the game process. Returns None if it can't be determined."""
    try:
        import psutil
    except ImportError:
        return None
    try:
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() == "valorant-win64-shipping.exe" or \
               (proc.info.get("name") or "").lower() == "valorant.exe":
                return True
    except Exception:  # psutil can raise a few platform specific errors here
        return None
    return False


def debug_environment():
    """Small summary used in debug logs."""
    return {
        "lockfile_exists": os.path.exists(riot_lockfile()),
        "log_exists": os.path.exists(shooter_game_log()),
    }
