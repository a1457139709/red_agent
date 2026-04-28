import main as main_module


def test_handle_help_command_supports_all_registered_topics():
    outputs: list[str] = []
    errors: list[str] = []

    assert main_module.handle_help_command(
        "/help report",
        text_output=outputs.append,
        error_output=errors.append,
    )

    assert errors == []
    assert "Help: report" in outputs[0]
    assert "Report Commands" in outputs[0]


def test_handle_help_command_reports_full_supported_topic_list_for_errors():
    outputs: list[str] = []
    errors: list[str] = []

    assert main_module.handle_help_command(
        "/help nope",
        text_output=outputs.append,
        error_output=errors.append,
    )

    assert outputs == []
    assert len(errors) == 1
    assert "Unknown help topic: nope." in errors[0]
    assert "Available topics:" in errors[0]
    assert "query, finding, artifact, report" in errors[0]
    assert "planner, skill, module" in errors[0]


def test_handle_help_command_rejects_task_topic():
    outputs: list[str] = []
    errors: list[str] = []

    assert main_module.handle_help_command(
        "/help task",
        text_output=outputs.append,
        error_output=errors.append,
    )

    assert outputs == []
    assert len(errors) == 1
    assert "Unknown help topic: task." in errors[0]


def test_handle_help_command_usage_lists_all_topics():
    outputs: list[str] = []
    errors: list[str] = []

    assert main_module.handle_help_command(
        "/help query extra",
        text_output=outputs.append,
        error_output=errors.append,
    )

    assert outputs == []
    assert len(errors) == 1
    assert "Usage: /help <topic>" in errors[0]
    assert "Available topics:" in errors[0]
