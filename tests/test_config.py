from hitrax import config


def test_repo_config_loads_with_swing_off():
    s = config.load()
    assert s.features.swing_tracking is False
    assert s.conditions.contact_height_in == 30


def test_swing_toggle_and_missing_sections(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[features]\nswing_tracking = true\n")
    s = config.load(p)
    assert s.features.swing_tracking is True
    assert s.conditions.elevation_ft == 0
    assert s.spin.base_rpm == 1000
