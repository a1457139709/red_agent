import pytest

from models.conversation_context import ConversationContext
from web.conversation_store import InMemoryConversationStore


def test_web_conversation_store_round_trips_context():
    store = InMemoryConversationStore()
    created = store.create_conversation()
    created.active_skill_name = "security-audit"
    store.save(created)

    loaded = store.get(created.conversation_id)

    assert loaded.conversation_id == created.conversation_id
    assert loaded.active_skill_name == "security-audit"


def test_web_conversation_store_clear_removes_context():
    store = InMemoryConversationStore()
    created = store.create_conversation()

    store.clear(created.conversation_id)

    with pytest.raises(ValueError):
        store.get(created.conversation_id)
