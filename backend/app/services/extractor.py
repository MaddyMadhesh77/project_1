from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass
class CandidateMemory:
    predicate: str  # location | preference | skill | goal
    value: str
    raw_text: str
    polarity: int = 1  # +1 asserts the value, -1 negates it (e.g. "hate" vs "like")


class Extractor(Protocol):
    def extract(self, utterance: str) -> list[CandidateMemory]: ...


# Non-greedy value capture bounded by a conjunction/punctuation lookahead, so
# "I live in Bangalore and I like Python" doesn't swallow the whole tail.
_STOP = r"(?=\s+(?:and|but)\b|[,;!?.]|$)"

_LOCATION_RE = re.compile(r"\bi live in ([a-zA-Z]+(?:\s[a-zA-Z]+)*?)" + _STOP, re.IGNORECASE)
_PREFERENCE_NEG_RE = re.compile(
    r"\bi (?:hate|dislike|don't like|do not like) ([a-zA-Z0-9+# ]+?)" + _STOP, re.IGNORECASE
)
_PREFERENCE_POS_RE = re.compile(r"\bi (?:like|love|enjoy|prefer) ([a-zA-Z0-9+# ]+?)" + _STOP, re.IGNORECASE)
_SKILL_RE = re.compile(
    r"\bi (?:know|can code in|am skilled in|am good at) ([a-zA-Z0-9+# ]+?)" + _STOP, re.IGNORECASE
)
_GOAL_RE = re.compile(r"\bi (?:want to|am trying to|am learning to|plan to) ([a-zA-Z ]+?)" + _STOP, re.IGNORECASE)


def _clean(value: str) -> str:
    return value.strip().rstrip(".!,;").strip()


def format_candidate_text(candidate: CandidateMemory) -> str:
    """Canonical stored-text format for a candidate, e.g. 'preference: not Python'.

    `parse_stored_text` below is this function's inverse -- services/features.py
    uses it to recover (predicate, value, polarity) from a retrieved memory's
    stored text for rule-based contradiction detection (DESIGN.md 6.4).
    """
    return f"{candidate.predicate}: {'not ' if candidate.polarity < 0 else ''}{candidate.value}"


def parse_stored_text(text: str) -> tuple[str, str, int]:
    predicate, _, rest = text.partition(": ")
    rest = rest.strip()
    if rest.lower().startswith("not "):
        return predicate, rest[4:].strip(), -1
    return predicate, rest, 1


class RuleBasedExtractor:
    """Regex/keyword matcher over a fixed predicate set: location, preference, skill, goal.

    Deterministic and cheap by design (DESIGN.md 6.1) -- an LLM-based
    extractor can be swapped in later behind the same Extractor protocol.
    """

    def extract(self, utterance: str) -> list[CandidateMemory]:
        candidates: list[CandidateMemory] = []

        for match in _LOCATION_RE.finditer(utterance):
            candidates.append(CandidateMemory("location", _clean(match.group(1)), utterance))

        for match in _PREFERENCE_NEG_RE.finditer(utterance):
            candidates.append(CandidateMemory("preference", _clean(match.group(1)), utterance, polarity=-1))

        for match in _PREFERENCE_POS_RE.finditer(utterance):
            candidates.append(CandidateMemory("preference", _clean(match.group(1)), utterance, polarity=1))

        for match in _SKILL_RE.finditer(utterance):
            candidates.append(CandidateMemory("skill", _clean(match.group(1)), utterance))

        for match in _GOAL_RE.finditer(utterance):
            candidates.append(CandidateMemory("goal", _clean(match.group(1)), utterance))

        return candidates
