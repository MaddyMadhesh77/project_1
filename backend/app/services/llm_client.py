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

    _NEGATION_MARKERS = {
        "not", "no", "never", "don't", "doesn't", "didn't", "won't", "wouldn't",
        "isn't", "wasn't", "aren't", "weren't", "hate", "hates", "hated",
        "dislike", "dislikes", "stopped", "quit",
    }

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
        # Deterministic heuristic (no model call): two statements sharing most
        # of their vocabulary are almost certainly about the same underlying
        # fact, so a difference between them is more likely a real polarity
        # flip ("I like Python" vs "I don't like Python" -- high overlap,
        # opposite meaning) than two statements that barely share any words,
        # which are probably about different things entirely and can both be
        # true at once. Overlap therefore scales the score *up*, not down.
        # A negation/negative-sentiment marker present on only one side is
        # the clearest deterministic signal of an actual polarity flip this
        # heuristic can detect, so it adds an extra bump on top of overlap.
        #
        # Known-wrong case: two statements that truly contradict but share
        # little vocabulary (e.g. "I'm a vegetarian" vs "I had a steak last
        # night") will under-score here -- there's no shared word to key off
        # of. This is an ambiguous-case fallback for when the rule-based
        # same-predicate/same-value polarity check doesn't apply (see
        # services/features.py), not a substitute for a real model judge
        # (ClaudeLLMClient.judge_contradiction).
        words_a = set(statement_a.lower().split())
        words_b = set(statement_b.lower().split())
        union = words_a | words_b
        overlap = len(words_a & words_b) / len(union) if union else 0.0

        score = 0.15 + 0.55 * overlap

        negated_a = bool(words_a & self._NEGATION_MARKERS)
        negated_b = bool(words_b & self._NEGATION_MARKERS)
        if negated_a != negated_b:
            score += 0.3

        return round(min(1.0, max(0.0, score)), 2)


def history_for_api(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """The Messages API requires the first message to be from the user. The
    client trims its transcript to the last N messages, and a send that
    failed earlier leaves an unanswered user turn -- either can make the
    trimmed history start with an assistant reply, which the API rejects."""
    start = next((i for i, m in enumerate(history) if m.get("role") == "user"), len(history))
    return history[start:]


class ClaudeLLMClient:
    def __init__(self, api_key: str, model: str = "claude-sonnet-5") -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def reply(self, message: str, history: list[dict[str, str]]) -> str:
        messages = [*history_for_api(history), {"role": "user", "content": message}]
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=512,
            # Thinking is on by default on Claude Sonnet 5 and its tokens count
            # toward max_tokens, which could cut a 1-3 sentence reply short.
            thinking={"type": "disabled"},
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
            max_tokens=16,
            # Same reason, but worse: with thinking on, an 8-token budget could
            # be spent before the number was written, so parsing failed and
            # every judgment silently fell back to 0.5.
            thinking={"type": "disabled"},
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
