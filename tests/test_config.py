import importlib

import backend.config as config


def test_config_env_overrides_are_bounded_and_reloadable(monkeypatch):
    env = {
        "LEXA_MAX_HISTORY": "2500",
        "LEXA_RATE_LIMIT_CHAT": "77",
        "LEXA_RATE_LIMIT_EXECUTE": "not-an-int",
        "LEXA_RATE_LIMIT_AUDIT_READ": "240",
        "LEXA_AGENT_MAX_STEPS": "12",
        "LEXA_AGENT_STEP_TIMEOUT": "5",
        "LEXA_TOOL_USE_ENABLED": "0",
        "LEXA_MAX_FILE_SIZE_MB": "3",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    loaded = importlib.reload(config)
    try:
        assert loaded.MAX_HISTORY == 1000
        assert loaded.RATE_LIMIT_CHAT == 77
        assert loaded.RATE_LIMIT_EXECUTE == 20
        assert loaded.RATE_LIMIT_AUDIT_READ == 240
        assert loaded.AGENT_MAX_STEPS == 12
        assert loaded.AGENT_STEP_TIMEOUT == 5
        assert loaded.TOOL_USE_ENABLED is False
        assert loaded.MAX_FILE_SIZE_MB == 3
        assert loaded.MAX_FILE_SIZE == 3 * 1024 * 1024
    finally:
        for key in env:
            monkeypatch.delenv(key, raising=False)
        importlib.reload(config)
