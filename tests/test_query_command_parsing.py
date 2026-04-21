from controller.contracts import RecordLookupKind, ReportType
from controller.record_query_parser import parse_record_query_command


def test_parse_record_query_command_supports_session_scoped_lookup_commands():
    history = parse_record_query_command("/history")
    steps = parse_record_query_command("/steps latest")
    artifacts = parse_record_query_command("/artifacts S0007")
    status_alias = parse_record_query_command("/s current")

    assert history is not None
    assert history.kind == RecordLookupKind.SESSION_HISTORY
    assert history.explicit_scope is None

    assert steps is not None
    assert steps.kind == RecordLookupKind.EXECUTION_STEPS
    assert steps.explicit_scope == "latest"

    assert artifacts is not None
    assert artifacts.kind == RecordLookupKind.ARTIFACTS
    assert artifacts.explicit_scope == "S0007"

    assert status_alias is not None
    assert status_alias.kind == RecordLookupKind.SESSION_HISTORY
    assert status_alias.explicit_scope == "current"


def test_parse_record_query_command_supports_show_why_and_report_flows():
    show_artifact = parse_record_query_command("/show A0004")
    show_session = parse_record_query_command("/show s0009")
    explain_finding = parse_record_query_command("/why F0003 latest")
    report = parse_record_query_command("/report operator_report S0002")

    assert show_artifact is not None
    assert show_artifact.kind == RecordLookupKind.ARTIFACTS
    assert show_artifact.lookup_identifier == "A0004"
    assert show_artifact.explicit_scope is None

    assert show_session is not None
    assert show_session.kind == RecordLookupKind.SESSION_HISTORY
    assert show_session.lookup_identifier == "S0009"
    assert show_session.explicit_scope == "S0009"

    assert explain_finding is not None
    assert explain_finding.kind == RecordLookupKind.FINDING_EXPLANATION
    assert explain_finding.lookup_identifier == "F0003"
    assert explain_finding.explicit_scope == "latest"

    assert report is not None
    assert report.kind == RecordLookupKind.REPORTS
    assert report.report_type == ReportType.OPERATOR_REPORT
    assert report.explicit_scope == "S0002"


def test_parse_record_query_command_preserves_legacy_report_commands_as_advanced_commands():
    assert parse_record_query_command("/report list S0001") is None
    assert parse_record_query_command("/report show RP0001") is None


def test_parse_record_query_command_rejects_invalid_usage():
    try:
        parse_record_query_command("/show")
    except ValueError as exc:
        assert "Usage: /show <public_id>" in str(exc)
    else:
        raise AssertionError("Expected /show without a public id to fail.")

    try:
        parse_record_query_command("/why A0001")
    except ValueError as exc:
        assert "Usage: /why <finding_public_id>" in str(exc)
    else:
        raise AssertionError("Expected /why with a non-finding id to fail.")

    try:
        parse_record_query_command("/history bogus")
    except ValueError as exc:
        assert "Usage: /history [current|latest|S0001]" in str(exc)
    else:
        raise AssertionError("Expected invalid scope hints to fail.")
