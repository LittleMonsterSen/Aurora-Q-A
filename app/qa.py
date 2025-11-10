import re
import os
from typing import Optional

from .memory_agent import (
    MemoryAgent,
    resolve_user_id,
    answer_with_memory,
)


class QASystem:
    def __init__(self, messages_api_base: str) -> None:
        self.messages_api_base = messages_api_base.rstrip("/")
        self.agent = MemoryAgent()

    async def answer(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "Please provide a non-empty question."

        # Extract a likely person name from the question. We support partial names like "Layla".
        name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", question)
        user_id: Optional[str] = None
        if name_match:
            candidate = name_match.group(1)
            resolved = await resolve_user_id(self.messages_api_base, candidate)
            if resolved:
                user_id = resolved[0]

        if not user_id:
            return "I don't know"

        return await answer_with_memory(self.agent, self.messages_api_base, question, user_id)

