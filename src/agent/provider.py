from langchain_openai import ChatOpenAI

from .settings import Settings, get_settings


def create_model(settings: Settings | None = None):
    settings = settings or get_settings()
    settings.validate_model_config()

    return ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.model_temperature,
        openai_api_key=settings.openai_api_key,
        openai_api_base=settings.openai_api_base,
    )

