import os
import re

from ivalocker.agents import ROLES, load_bundled, merge
from ivalocker.paths import resource_path

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def test_bundled_roster_is_complete_and_consistent():
    agents = load_bundled()
    names = {a["name"] for a in agents}
    assert {"Veto", "Miks", "Waylay", "Tejo"} <= names
    assert len({a["uuid"] for a in agents}) == len(agents)
    for agent in agents:
        assert UUID_RE.match(agent["uuid"]), agent
        assert agent["role"] in ROLES, agent
        assert re.match(r"^#[0-9a-f]{6}$", agent["color"]), agent
        for key in ("banner", "preview"):
            path = resource_path("web", *agent[key].lstrip("./").split("/"))
            assert os.path.isfile(path), f"missing {key} for {agent['name']}: {path}"


def _api_entry(name, uuid, role="Duelist"):
    return {"displayName": name, "uuid": uuid, "role": {"displayName": role}, "isPlayableCharacter": True,
            "backgroundGradientColors": ["ff0000ff"], "fullPortrait": "https://example/p.png"}


def test_merge_adds_unknown_agents_only():
    bundled = [{"name": "Jett", "uuid": "a" * 8 + "-0000-0000-0000-" + "0" * 12, "role": "Duelist"}]
    merged = merge(bundled, [
        _api_entry("Jett", bundled[0]["uuid"]),
        _api_entry("Newbie", "b" * 8 + "-0000-0000-0000-" + "0" * 12, "Sentinel"),
        {"displayName": "Sova", "uuid": "c" * 8 + "-0000-0000-0000-" + "0" * 12, "isPlayableCharacter": False},
        {"garbage": True},
    ])
    assert [a["name"] for a in merged] == ["Jett", "Newbie"]
    assert merged[1]["role"] == "Sentinel"
    assert merged[1]["color"] == "#ff0000"
    assert merged[1]["bundled"] is False


def test_merge_prefers_live_uuid_for_known_name():
    old = "a" * 8 + "-0000-0000-0000-" + "0" * 12
    new = "d" * 8 + "-0000-0000-0000-" + "0" * 12
    bundled = [{"name": "Miks", "uuid": old, "role": "Controller", "banner": "local.webp"}]
    merged = merge(bundled, [_api_entry("Miks", new, "Controller")])
    assert len(merged) == 1
    assert merged[0]["uuid"] == new
    assert merged[0]["banner"] == "local.webp"
    assert bundled[0]["uuid"] == old  # input is not mutated
