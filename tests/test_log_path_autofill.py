from src.utils.log_path_detector import fill_missing_client_log_paths


def test_fill_missing_client_log_paths_preserves_manual_value(monkeypatch):
    config = {"client_log_paths": {"poe1": "D:/manual/Client.txt", "poe2": ""}}
    monkeypatch.setattr(
        "src.utils.log_path_detector.detect_client_log_paths",
        lambda: {"poe1": "C:/auto/poe1/Client.txt", "poe2": "C:/auto/poe2/Client.txt"},
    )

    assert fill_missing_client_log_paths(config) is True
    assert config["client_log_paths"] == {
        "poe1": "D:/manual/Client.txt",
        "poe2": "C:/auto/poe2/Client.txt",
    }


def test_fill_missing_client_log_paths_repairs_cross_saved_known_install(monkeypatch):
    poe1_path = r"C:\Program Files\Epic Games\PathOfExile\logs\Client.txt"
    poe2_path = r"C:\Program Files\Epic Games\PathOfExile2\logs\Client.txt"
    config = {"client_log_paths": {"poe1": poe2_path, "poe2": poe2_path}}
    monkeypatch.setattr(
        "src.utils.log_path_detector.detect_client_log_paths",
        lambda: {"poe1": poe1_path, "poe2": poe2_path},
    )

    assert fill_missing_client_log_paths(config) is True
    assert config["client_log_paths"] == {
        "poe1": poe1_path,
        "poe2": poe2_path,
    }
