import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import dotenv

DEFAULT_MAX_AGENT_STEPS = 50
DEFAULT_CONTEXT_TOKEN_LIMIT = 128000
DEFAULT_COMPRESSION_THRESHOLD = 0.8
DEFAULT_SYSTEM_PROMPT_RESERVE = 2000
DEFAULT_MODEL_TEMPERATURE = 0.5


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_api_base: str | None
    openai_model: str | None
    openai_reasoning_effort: str | None = None
    model_temperature: float = DEFAULT_MODEL_TEMPERATURE
    max_agent_steps: int = DEFAULT_MAX_AGENT_STEPS
    context_token_limit: int = DEFAULT_CONTEXT_TOKEN_LIMIT
    compression_threshold: float = DEFAULT_COMPRESSION_THRESHOLD
    system_prompt_reserve: int = DEFAULT_SYSTEM_PROMPT_RESERVE
    working_directory: Path = Path.cwd().resolve()

    @property
    def app_data_dir(self) -> Path:
        return self.working_directory / ".red-code"

    @property
    def sqlite_path(self) -> Path:
        return self.app_data_dir / "agent.db"

    @property
    def checkpoints_dir(self) -> Path:
        return self.app_data_dir / "checkpoints"

    @property
    def skills_dir(self) -> Path:
        return self.app_data_dir / "skills"

    @classmethod
    def from_env(cls) -> "Settings":
        dotenv.load_dotenv()
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_api_base=os.getenv("OPENAI_API_BASE"),
            openai_model=os.getenv("OPENAI_MODEL"),
            openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT"),
            model_temperature=float(os.getenv("MODEL_TEMPERATURE", DEFAULT_MODEL_TEMPERATURE)),
            max_agent_steps=int(os.getenv("MAX_AGENT_STEPS", DEFAULT_MAX_AGENT_STEPS)),
            context_token_limit=int(os.getenv("MODEL_CONTEXT_TOKEN_LIMIT", DEFAULT_CONTEXT_TOKEN_LIMIT)),
            compression_threshold=float(os.getenv("COMPRESSION_THRESHOLD", DEFAULT_COMPRESSION_THRESHOLD)),
            system_prompt_reserve=int(os.getenv("SYSTEM_PROMPT_RESERVE", DEFAULT_SYSTEM_PROMPT_RESERVE)),
            working_directory=Path.cwd().resolve(),
        )

    def validate_model_config(self) -> None:
        if not self.openai_model:
            raise ValueError("缺少 OPENAI_MODEL 配置")
        if not self.openai_api_key:
            raise ValueError("缺少 OPENAI_API_KEY 配置")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
