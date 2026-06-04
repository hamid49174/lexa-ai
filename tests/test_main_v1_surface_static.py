from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_v1_local_control_plane_mirror_is_legacy_opt_in():
    src = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")

    assert "LEXA_ENABLE_LOCAL_V1_ROUTERS" in src
    assert "_enable_legacy_local_v1" in src
    assert src.count("_v1_router.include_router(stripe_router)") == 1
    assert src.count("_v1_router.include_router(health_router)") == 1

    for router_name in [
        "chat_router",
        "memory_router",
        "backup_router",
        "companion_router",
        "agent_router",
        "hermes_router",
        "os_agents_router",
        "personal_os_router",
    ]:
        include = f"_v1_router.include_router({router_name})"
        assert include in src
        assert src.rfind("if _enable_legacy_local_v1:", 0, src.index(include)) >= 0
