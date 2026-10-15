import base64
import json

from ivalocker.riot import (decode_presence, find_player, parse_client_version, parse_lockfile, parse_region,
                            summarize_presence)


def test_parse_lockfile():
    lock = parse_lockfile("Riot Client:1234:51234:s3cr3t:https\n")
    assert lock == {"name": "Riot Client", "pid": "1234", "port": 51234, "password": "s3cr3t", "protocol": "https"}


def test_parse_region_prefers_latest_glz_url():
    log = (b"URL [GET https://glz-na-1.na.a.pvp.net/parties/v1/players/x]\n"
           b"URL [GET https://glz-latam-1.na.a.pvp.net/parties/v1/players/x]\n")
    assert parse_region(log) == ("latam", "na")


def test_parse_region_legacy_formats():
    assert parse_region(b"https://shared.ap.a.pvp.net/v1/config/ap]") == ("ap", "ap")
    assert parse_region(b"something regions/br] more") == ("br", "na")
    assert parse_region(b"nothing useful") == (None, None)


def test_parse_client_version():
    log = b"LogShooter: Display: CI server version: release-11.07-shipping-6-3519467\r\n"
    assert parse_client_version(log) == "release-11.07-shipping-6-3519467"
    assert parse_client_version(b"") is None


def _encode(data):
    return base64.b64encode(json.dumps(data).encode()).decode()


def test_presence_new_format():
    presence = decode_presence(_encode({
        "matchPresenceData": {"sessionLoopState": "PREGAME", "queueId": "competitive"},
        "partyPresenceData": {"partyState": "DEFAULT"},
    }))
    assert summarize_presence(presence) == {"loop_state": "PREGAME", "party_state": "DEFAULT", "queue": "competitive"}


def test_presence_old_format_and_garbage():
    presence = decode_presence(_encode({"sessionLoopState": "MENUS", "partyState": "MATCHMAKING", "queueId": "unrated"}))
    assert summarize_presence(presence) == {"loop_state": "MENUS", "party_state": "MATCHMAKING", "queue": "unrated"}
    assert decode_presence("not base64 json") is None
    assert summarize_presence(None)["loop_state"] is None


def test_find_player():
    match = {"AllyTeam": {"Players": [{"Subject": "a"}, {"Subject": "me", "CharacterSelectionState": "locked"}]}}
    assert find_player(match, "me")["CharacterSelectionState"] == "locked"
    assert find_player({"Teams": [{"Players": [{"Subject": "me"}]}]}, "me") == {"Subject": "me"}
    assert find_player({}, "me") is None
