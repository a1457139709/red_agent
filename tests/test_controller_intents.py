from controller.contracts import ClarificationKind, ControllerIntent
from controller.intents import classify_input, extract_record_scope, extract_targets
from models.session import SessionTargetKind


def test_classify_input_detects_top_level_intents():
    assert classify_input("/task list").intent == ControllerIntent.ADVANCED_COMMAND_REQUEST
    assert classify_input("Summarize this repository structure").intent == ControllerIntent.NORMAL_REQUEST
    assert classify_input("Start a recon session for example.com").intent == ControllerIntent.REDTEAM_REQUEST
    assert classify_input("What did you already do?").intent == ControllerIntent.RECORD_LOOKUP_REQUEST


def test_classify_input_marks_ambiguous_requests_for_clarification():
    bare_target = classify_input("look at example.com")
    missing_target = classify_input("scan this host")

    assert bare_target.intent == ControllerIntent.CLARIFICATION_REQUIRED
    assert bare_target.clarification_kind == ClarificationKind.BARE_TARGET
    assert bare_target.extracted_targets[0].value == "example.com"

    assert missing_target.intent == ControllerIntent.CLARIFICATION_REQUIRED
    assert missing_target.clarification_kind == ClarificationKind.MISSING_TARGET


def test_classify_input_rejects_unsupported_noise():
    unsupported = classify_input("???")

    assert unsupported.intent == ControllerIntent.UNSUPPORTED_REQUEST
    assert unsupported.unsupported_reason is not None


def test_extract_targets_and_record_scope_handle_common_shapes():
    targets = extract_targets("Inspect https://example.com and 10.0.0.0/24 via 93.184.216.34")

    assert [target.kind for target in targets] == [
        SessionTargetKind.URL,
        SessionTargetKind.CIDR,
        SessionTargetKind.IP,
    ]
    assert extract_record_scope("show me session S0007") == "S0007"
    assert extract_record_scope("show me the latest session") == "latest"
