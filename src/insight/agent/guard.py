"""Input guard: flag prompt-injection and data-exfiltration attempts.

The guard is a signal (logged, shown to the user, counted in AI KPIs), not the main defence.
The main defences are architectural: the planner can only output a structured metric query,
the compiler only uses catalog identifiers and bound parameters, row-level access is applied
in the compiler, and the warehouse connection is read-only with no external access.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore-instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(instructions?|rules|guardrails?|polic(y|ies)|restrictions?|filters?|access)\b",
            re.I,
        ),
    ),
    ("reveal-prompt", re.compile(r"\b(reveal|print|show|repeat|leak)\b.{0,30}\b(system prompt|your (instructions|rules|prompt))\b", re.I)),
    (
        "role-override",
        re.compile(r"\b(you are now|act as (an? )?(admin|administrator|dba)|developer mode|jailbreak|pretend (to be|you are))\b", re.I),
    ),
    (
        "raw-sql",
        re.compile(
            r"\b(drop|delete|insert|update|alter|truncate|attach|copy)\b\s+(table|from|into|database|schema)\b|;\s*--|\bunion\s+select\b|\bread_csv\b|\bpragma\b",
            re.I,
        ),
    ),
    ("access-escalation", re.compile(r"\b(all countries|every country|other countries|unrestricted|without (the )?(filter|restriction)s?)\b", re.I)),
    ("german-override", re.compile(r"\b(ignoriere|vergiss|umgehe)\b.{0,40}\b(anweisungen|regeln|filter|beschränkungen)\b", re.I)),
]


@dataclass
class GuardResult:
    flagged: bool
    patterns: list[str] = field(default_factory=list)


def screen(question: str) -> GuardResult:
    hits = [name for name, rx in PATTERNS if rx.search(question)]
    return GuardResult(flagged=bool(hits), patterns=hits)
