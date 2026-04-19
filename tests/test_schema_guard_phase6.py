import sqlite3

import pytest

from agent.settings import Settings
from storage.repositories.artifacts import ArtifactRepository
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_phase6_schema_guard_requires_clean_runtime_reset(tmp_path):
    settings = build_settings(tmp_path)
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.sqlite_path) as connection:
        connection.execute("CREATE TABLE evidence (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO evidence (id) VALUES ('legacy-1')")
        connection.commit()

    with pytest.raises(ValueError) as excinfo:
        ArtifactRepository(SQLiteStorage(settings.sqlite_path))

    assert "test-only and can be recreated" in str(excinfo.value)
    assert "Delete `.red-code/agent.db`" in str(excinfo.value)
