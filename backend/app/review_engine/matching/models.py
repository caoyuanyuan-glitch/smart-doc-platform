from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class MatchResult:
    match_level: str
    score: float
    matched_span: str
    rule_id: str
    evidence: str
    protected_literal_diff: list[str]
    rejected_reason: str = ""
    is_candidate: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
