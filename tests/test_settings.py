from ivalocker.settings import Settings


def test_settings_validate_and_persist(tmp_path):
    path = str(tmp_path / "settings.json")
    s = Settings(path=path)
    s.update({"mode": "nonsense", "lock_delay_ms": "99999", "poll": "fast", "unknown": 1, "favorites": ["Jett"]})
    assert s["mode"] == "lock"
    assert s["lock_delay_ms"] == 5000
    assert s.poll_interval == 0.05

    reloaded = Settings(path=path)
    assert reloaded["favorites"] == ["Jett"]
    assert "unknown" not in reloaded.as_dict()


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert Settings(path=str(path))["mode"] == "lock"
