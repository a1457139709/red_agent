from models.risk_policy import ConfirmationMode, RiskLevel


def test_risk_levels_are_stable():
    assert [level.value for level in RiskLevel] == ["safe", "elevated", "dangerous"]


def test_confirmation_modes_are_stable():
    assert [mode.value for mode in ConfirmationMode] == ["auto", "confirm"]
