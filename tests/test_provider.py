import agent.provider as provider_module
from agent.settings import Settings


def test_create_model_passes_reasoning_effort(monkeypatch, tmp_path):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(provider_module, "ChatOpenAI", FakeChatOpenAI)

    settings = Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        openai_reasoning_effort="high",
        working_directory=tmp_path,
    )

    provider_module.create_model(settings)

    assert captured["model"] == "test-model"
    assert captured["reasoning_effort"] == "high"
