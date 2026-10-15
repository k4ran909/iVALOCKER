from ivalocker.hotkeys import MOD_ALT, MOD_CONTROL, normalize, parse
from ivalocker.settings import Settings


def test_parse_and_normalize():
    assert parse("F8") == ("F8", 0, 0x77)
    assert parse("ctrl+alt+l") == ("Ctrl+Alt+L", MOD_CONTROL | MOD_ALT, ord("L"))
    assert normalize("alt + ctrl + numpad5") == "Ctrl+Alt+Numpad5"
    assert normalize("Shift+pageup") == "Shift+PageUp"
    assert normalize("Ctrl+\\") == "Ctrl+\\"


def test_rejects_keys_that_would_block_typing_or_garbage():
    for spec in ("A", "5", "Space", "Up", "Ctrl+", "Ctrl+Ctrl+A", "Hyper+A", "F25", "", None, 5):
        assert normalize(spec) == "", spec


def test_settings_store_canonical_hotkeys(tmp_path):
    s = Settings(path=str(tmp_path / "settings.json"))
    assert s["hotkey_arm"] == "F8"
    s.update({"hotkey_arm": "ctrl+shift+k", "hotkey_next": "Q", "hotkey_mode": ""})
    assert s["hotkey_arm"] == "Ctrl+Shift+K"
    assert s["hotkey_next"] == ""  # a bare letter is rejected
    assert s["hotkey_mode"] == ""
