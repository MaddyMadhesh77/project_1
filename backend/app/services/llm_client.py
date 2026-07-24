from __future__ import annotations

import random
from typing import Protocol

from app.core.config import Settings


class LLMClient(Protocol):
    async def reply(self, message: str, history: list[dict[str, str]]) -> str: ...

    async def judge_contradiction(self, statement_a: str, statement_b: str) -> float:
        """Return 0 (fully consistent) .. 1 (direct contradiction). Ambiguous-case
        fallback used by services/features.py when the rule-based negation/antonym
        check (same predicate + same value + polarity flip) doesn't cleanly apply
        (DESIGN.md 6.4)."""
        ...


class TemplatedLLMClient:
    """Canned, fully deterministic replies. No API key needed -- good for rehearsed demos."""

    _ACKS = [
        "Got it, I'll remember that.",
        "Noted, thanks for letting me know.",
        "Okay, I've taken that on board.",
        "Understood.",
    ]

    async def reply(self, message: str, history: list[dict[str, str]]) -> str:
        if "?" in message:
            return (
                "That's a good question -- I don't have a live model wired up in this "
                "demo, but I've noted what you told me."
            )
        return random.choice(self._ACKS)

    async def judge_contradiction(self, statement_a: str, statement_b: str) -> float:
        # Deterministic heuristic (no model call): more shared words between the
        # two statements suggests they're about the same underlying fact and an
        # update to it (moderate contradiction); little overlap suggests an
        # unrelated correction rather than a hard contradiction.
        words_a = set(statement_a.lower().split())
        words_b = set(statement_b.lower().split())
        union = words_a | words_b
        overlap = len(words_a & words_b) / len(union) if union else 0.0
        return round(0.6 - 0.3 * overlap, 2)


class ClaudeLLMClient:
    def __init__(self, api_key: str, model: str = "claude-sonnet-5") -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def reply(self, message: str, history: list[dict[str, str]]) -> str:
        messages = [*history, {"role": "user", "content": message}]
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=(
                "You are a warm, concise personal assistant chatting with a user. "
                "Keep replies to 1-3 sentences."
            ),
            messages=messages,
        )
        return "".join(block.text for block in response.content if block.type == "text")

    async def judge_contradiction(self, statement_a: str, statement_b: str) -> float:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=8,
            system=(
                "You judge whether two short factual statements about the same person "
                "contradict each other. Reply with ONLY a number from 0 to 1: 0 means fully "
                "consistent/corroborating, 1 means a direct contradiction. No words, just the number."
            ),
            messages=[{"role": "user", "content": f"Statement A: {statement_a}\nStatement B: {statement_b}"}],
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        try:
            return max(0.0, min(1.0, float(text)))
        except ValueError:
            return 0.5


def get_llm_client(settings: Settings) -> LLMClient:
    if settings.anthropic_api_key:
        return ClaudeLLMClient(api_key=settings.anthropic_api_key)
    return TemplatedLLMClient()
