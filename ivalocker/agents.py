"""
Agent roster.

The bundled roster (web/json/agents.json) works fully offline and ships with local artwork.
On startup we also try valorant-api.com so agents released after this build show up
automatically (with remote artwork). The live list is cached for offline use.
"""
import json
import logging
import os

import requests

from .paths import data_dir, resource_path

logger = logging.getLogger(__name__)

AGENTS_API = "https://valorant-api.com/v1/agents?isPlayableCharacter=true"
CACHE_FILE = "agents_cache.json"

# The agents every account starts with. They never show up in the store entitlements.
STARTER_AGENTS = {
    "add6443a-41bd-e414-f6ad-e58d267f4e95",  # Jett
    "eb93336a-449b-9c1b-0a54-a891f7921d69",  # Phoenix
    "569fdd95-4d10-43ab-ca70-79becc718b46",  # Sage
    "320b2a48-4d9b-a075-30f1-1f93a9b638fa",  # Sova
    "9f0d8ba9-4140-b941-57d3-a7ad57c6b417",  # Brimstone
}

ROLES = ("Duelist", "Initiator", "Controller", "Sentinel")


def load_bundled():
    with open(resource_path("web", "json", "agents.json"), encoding="utf-8") as f:
        agents = json.load(f)
    for agent in agents:
        agent["uuid"] = agent["uuid"].lower()
        agent.setdefault("banner", f"./assets/images/agent-banners/{agent['name'].lower()}.webp")
        agent.setdefault("preview", f"./assets/images/agent-previews/{agent['name'].lower()}.webp")
        agent["bundled"] = True
    return agents


def _from_api(entry):
    """Convert one valorant-api.com agent entry into our roster format."""
    colors = entry.get("backgroundGradientColors") or []
    color = "#" + colors[0][:6] if colors and isinstance(colors[0], str) else "#ff4655"
    role = (entry.get("role") or {}).get("displayName") or "Unknown"
    portrait = entry.get("fullPortrait") or entry.get("displayIcon")
    return {
        "name": entry["displayName"],
        "uuid": entry["uuid"].lower(),
        "role": role,
        "color": color,
        "banner": entry.get("background") or portrait,
        "portrait": portrait,
        "preview": portrait,
        "bundled": False,
    }


def merge(bundled, remote_entries):
    """Add agents that only exist in the live list. Bundled agents keep their local artwork."""
    known = {a["uuid"] for a in bundled}
    merged = list(bundled)
    for entry in remote_entries:
        try:
            if not entry.get("isPlayableCharacter", True):
                continue
            agent = _from_api(entry)
        except (KeyError, AttributeError, TypeError):
            continue
        if agent["uuid"] not in known:
            known.add(agent["uuid"])
            merged.append(agent)
    return merged


class Roster:

    def __init__(self):
        self.agents = load_bundled()
        self._apply_cache()

    def _apply_cache(self):
        try:
            with open(os.path.join(data_dir(), CACHE_FILE), encoding="utf-8") as f:
                self.agents = merge(self.agents, json.load(f))
        except (OSError, ValueError):
            pass

    def refresh_from_api(self):
        """Fetch the live agent list. Returns True if new agents were added."""
        try:
            r = requests.get(AGENTS_API, timeout=6)
            r.raise_for_status()
            entries = r.json().get("data") or []
        except (requests.RequestException, ValueError, AttributeError) as e:
            logger.info("Live agent list unavailable: %s", e)
            return False

        try:
            with open(os.path.join(data_dir(), CACHE_FILE), "w", encoding="utf-8") as f:
                json.dump(entries, f)
        except OSError:
            pass

        before = len(self.agents)
        self.agents = merge(self.agents, entries)
        return len(self.agents) > before

    def by_name(self, name):
        if not name:
            return None
        name = name.lower()
        return next((a for a in self.agents if a["name"].lower() == name), None)

    def as_list(self):
        return sorted(self.agents, key=lambda a: a["name"].lower())
