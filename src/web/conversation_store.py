from __future__ import annotations

from dataclasses import replace

from models.conversation_context import ConversationContext


class InMemoryConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, ConversationContext] = {}

    def create_conversation(self) -> ConversationContext:
        context = ConversationContext()
        self.save(context)
        return replace(context)

    def get(self, conversation_id: str) -> ConversationContext:
        try:
            context = self._conversations[conversation_id]
        except KeyError as exc:
            raise ValueError(f"Conversation not found: {conversation_id}") from exc
        return replace(context)

    def save(self, context: ConversationContext) -> None:
        self._conversations[context.conversation_id] = replace(context)

    def clear(self, conversation_id: str) -> None:
        self._conversations.pop(conversation_id, None)
