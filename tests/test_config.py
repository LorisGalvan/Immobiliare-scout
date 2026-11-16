from scout.config import load_config


def test_override_locale(tmp_path):
    (tmp_path / "config.yaml").write_text("a: 1\nalert:\n  telegram:\n    attivo: false\n    token: ''\n")
    (tmp_path / "config.local.yaml").write_text("alert:\n  telegram:\n    token: XYZ\n")
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg["a"] == 1 and cfg["alert"]["telegram"]["token"] == "XYZ"
    assert cfg["alert"]["telegram"]["attivo"] is False
