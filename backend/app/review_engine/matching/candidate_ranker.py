from __future__ import annotations

from app.review_engine.matching.lexical import bigram_score, lcs_length
from app.review_engine.matching.models import MatchResult
from app.review_engine.matching.normalize import canonical_span, normalize_text
from app.review_engine.matching.protected_literals import protected_literal_diff
from app.review_engine.matching.structure import structures_compatible


def rank_candidate(rule_text: str, document_span: str, *, rule_id: str = "", match_level: str = "fuzzy") -> MatchResult:
    left = normalize_text(rule_text)
    right = normalize_text(document_span)
    if not right:
        return MatchResult(
            match_level=match_level,
            score=0,
            matched_span="",
            rule_id=rule_id,
            evidence="",
            protected_literal_diff=[],
            rejected_reason="no_actionable_evidence",
            is_candidate=True,
        )
    if match_level in {"exact", "regex"} and left and left in right:
        return MatchResult(
            match_level=match_level,
            score=1.0,
            matched_span=right,
            rule_id=rule_id,
            evidence=right,
            protected_literal_diff=[],
            is_candidate=False,
        )
    diffs = protected_literal_diff(left, right)
    if diffs:
        return MatchResult(
            match_level="fuzzy",
            score=0,
            matched_span=right,
            rule_id=rule_id,
            evidence=right,
            protected_literal_diff=diffs,
            rejected_reason="protected_literal_mismatch",
            is_candidate=True,
        )
    if not structures_compatible(left, right):
        return MatchResult(
            match_level="fuzzy",
            score=0,
            matched_span=right,
            rule_id=rule_id,
            evidence=right,
            protected_literal_diff=[],
            rejected_reason="structure_mismatch",
            is_candidate=True,
        )
    score = max(bigram_score(canonical_span(left), canonical_span(right)), lcs_length(left, right) / max(len(left), len(right), 1))
    if score < 0.55:
        return MatchResult(
            match_level="fuzzy",
            score=score,
            matched_span=right,
            rule_id=rule_id,
            evidence="",
            protected_literal_diff=[],
            rejected_reason="no_actionable_evidence",
            is_candidate=True,
        )
    return MatchResult(
        match_level="fuzzy",
        score=score,
        matched_span=right,
        rule_id=rule_id,
        evidence=right,
        protected_literal_diff=[],
        is_candidate=True,
    )
