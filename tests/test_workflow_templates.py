from backend.workflow_templates import get_all_templates, get_template_by_name


def test_workflow_templates_have_stable_unique_ids_and_names():
    templates = get_all_templates()
    names = [template["name"] for template in templates]
    template_ids = [template["template_id"] for template in templates]

    assert len(templates) == 5
    assert len(names) == len(set(names))
    assert len(template_ids) == len(set(template_ids))
    assert set(template_ids) == {
        "morgen-routine",
        "pomodoro-auto",
        "backup-reminder",
        "high-cpu-alert",
        "projekt-setup",
    }


def test_workflow_template_lookup_returns_expected_template_or_none():
    template = get_template_by_name("Pomodoro-Auto")

    assert template is not None
    assert template["template_id"] == "pomodoro-auto"
    assert template["trigger"] == {"type": "event", "event": "system_start"}
    assert template["steps"][1]["tool"] == "pomodoro_start"
    assert get_template_by_name("Unbekannt") is None


def test_workflow_templates_are_importable_workflow_dicts():
    for template in get_all_templates():
        assert template["description"]
        assert isinstance(template["trigger"], dict)
        assert isinstance(template["steps"], list)
        assert template["steps"]
        assert all("type" in step for step in template["steps"])
