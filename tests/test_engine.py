import pytest

import ivalocker.engine as engine_module
from ivalocker.engine import Engine, game_label, map_name
from ivalocker.riot import ApiError
from ivalocker.settings import Settings

JETT = "add6443a-41bd-e414-f6ad-e58d267f4e95"
REYNA = "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc"


class FakeRoster:
    agents = [{"name": "Jett", "uuid": JETT}, {"name": "Reyna", "uuid": REYNA}]

    def by_name(self, name):
        return next((a for a in self.agents if name and a["name"].lower() == name.lower()), None)


class FakeClient:
    puuid = "me"

    def __init__(self):
        self.connected = True
        self.loop_state = "MENUS"
        self.taken = set()
        self.calls = []

    def fetch_presence(self):
        return {"matchPresenceData": {"sessionLoopState": self.loop_state, "queueId": "competitive"}}

    def ensure_fresh_tokens(self):
        pass

    def pregame_match_id(self):
        self.calls.append("match_id")
        return "match-1" if self.loop_state == "PREGAME" else None

    def _respond(self, action, agent):
        self.calls.append((action, agent))
        if agent in self.taken:
            raise ApiError(409, {"errorCode": "CHARACTER_UNAVAILABLE"})
        state = "locked" if action == "lock" else "selected"
        return {"MapID": "/Game/Maps/Ascent/Ascent", "QueueID": "competitive",
                "AllyTeam": {"Players": [{"Subject": "me", "CharacterID": agent, "CharacterSelectionState": state}]}}

    def lock_agent(self, match_id, agent):
        return self._respond("lock", agent)

    def select_agent(self, match_id, agent):
        return self._respond("select", agent)


@pytest.fixture
def make_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_module, "_game_running", lambda: True)

    def factory(**settings):
        s = Settings(path=str(tmp_path / "settings.json"))
        s.update(settings)
        events = []
        eng = Engine(FakeRoster(), s, emit=lambda kind, payload: events.append((kind, payload)), client=FakeClient())
        return eng, eng.client, events
    return factory


def test_locks_agent_when_agent_select_starts(make_engine):
    eng, client, events = make_engine()
    eng.arm("Jett")
    assert eng.phase == "armed"

    eng._tick()
    assert ("lock", JETT) not in client.calls  # still in menus

    client.loop_state = "PREGAME"
    eng._tick()
    assert ("lock", JETT) in client.calls
    assert eng.phase == "locked"
    assert eng.armed is False  # keep_armed is off
    assert eng.result["map"] == "Ascent"
    assert eng.stats["locks"] == 1
    assert any(kind == "locked" for kind, _ in events)


def test_switching_agent_while_armed_locks_the_new_one(make_engine):
    eng, client, _ = make_engine()
    eng.arm("Jett")
    eng.set_agent("Reyna")
    client.loop_state = "PREGAME"
    eng._tick()
    assert ("lock", REYNA) in client.calls
    assert ("lock", JETT) not in client.calls


def test_backup_agent_used_when_main_is_taken(make_engine):
    eng, client, _ = make_engine(backup_agent="Reyna")
    client.taken = {JETT}
    eng.arm("Jett")
    client.loop_state = "PREGAME"
    eng._tick()
    assert eng.result["agent"] == "Reyna"
    assert eng.result["backup"] is True
    assert ("select", JETT) not in client.calls  # 409 doesn't trigger a pointless select retry


def test_hover_mode_only_selects(make_engine):
    eng, client, _ = make_engine(mode="hover")
    eng.arm("Jett")
    client.loop_state = "PREGAME"
    eng._tick()
    assert client.calls[-1] == ("select", JETT)
    assert eng.phase == "hovered"
    assert eng.stats["locks"] == 0


def test_keep_armed_handles_each_match_once(make_engine):
    eng, client, _ = make_engine(keep_armed=True)
    eng.arm("Jett")
    client.loop_state = "PREGAME"
    for _ in range(5):
        eng._tick()
    assert client.calls.count(("lock", JETT)) == 1
    assert eng.armed is True

    client.loop_state = "INGAME"
    eng._tick()
    assert eng.phase == "armed"


def test_failure_when_everything_is_taken(make_engine):
    eng, client, events = make_engine()
    client.taken = {JETT}
    eng.arm("Jett")
    client.loop_state = "PREGAME"
    eng._tick()
    assert eng.phase == "failed"
    assert eng.armed is False
    assert any(kind == "toast" for kind, _ in events)


def test_disarm(make_engine):
    eng, client, _ = make_engine()
    eng.arm("Jett")
    eng.disarm()
    client.loop_state = "PREGAME"
    eng._tick()
    assert not any(isinstance(c, tuple) for c in client.calls)
    assert eng.phase == "idle"


def test_labels():
    assert map_name("/Game/Maps/Triad/Triad") == "Haven"
    assert map_name("/Game/Maps/NewMap/NewMap") == "NewMap"
    assert game_label({"loop_state": "MENUS", "party_state": "MATCHMAKING"}) == "In queue"
    assert game_label({"loop_state": "PREGAME"}) == "Agent select"


def test_toggle_arm_uses_current_agent(make_engine):
    eng, client, events = make_engine()
    eng.toggle_arm()
    assert eng.armed is False
    assert any(kind == "toast" for kind, _ in events)  # no agent picked yet

    eng.set_agent("Reyna")  # arm_on_click is on by default -> armed
    assert eng.armed is True
    eng.toggle_arm()
    assert eng.armed is False
    eng.toggle_arm()
    assert eng.armed is True and eng.agent == "Reyna"


def test_cycle_favorite(make_engine):
    eng, client, _ = make_engine(favorites=["Jett", "Reyna"], arm_on_click=False)
    eng.cycle_favorite()
    assert eng.agent == "Jett" and eng.armed is False
    eng.cycle_favorite()
    assert eng.agent == "Reyna"
    eng.arm("Reyna")
    eng.cycle_favorite()
    assert eng.agent == "Jett" and eng.armed is True  # switching while armed keeps it armed


def test_toggle_mode(make_engine):
    eng, _, _ = make_engine()
    assert eng.toggle_mode() == "hover"
    assert eng.settings["mode"] == "hover"
    assert eng.toggle_mode() == "lock"
