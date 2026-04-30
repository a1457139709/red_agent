import main as main_module


def test_startup_banner_describes_command_driven_redteam_flow():
    banner = main_module.format_startup_banner()

    assert "RED-CODE 0.1.0" in banner
    assert "Command-driven local agent" in banner
    assert "/help" in banner
    assert "/redteam" in banner
    assert "/normal" in banner
    assert "Redteam mode:" in banner
    assert "AI-assisted automated testing" in banner
    assert "describe what you want" not in banner
    assert "advanced help" not in banner


def test_print_startup_banner_uses_supplied_output():
    outputs: list[str] = []

    main_module.print_startup_banner(outputs.append)

    assert outputs == [main_module.format_startup_banner()]
