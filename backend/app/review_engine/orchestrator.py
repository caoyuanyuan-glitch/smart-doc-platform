"""Minimal adapters so review_engine exports real callables."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.review_engine.pipeline import select_review_issues


@dataclass
class ReviewRunResult:
    issues: list[Any] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)


class ReviewOrchestrator:
    def run(self, issues, **kwargs) -> ReviewRunResult:
        selected = select_review_issues(issues, **kwargs) if kwargs else select_review_issues(issues)
        return ReviewRunResult(issues=list(selected or []))


class AICandidateEngine:
    def collect(self, issues) -> list[Any]:
        return [issue for issue in (issues or []) if str(getattr(issue, "source", None) or (issue.get("source") if isinstance(issue, dict) else "") or "").lower() == "ai"]


@dataclass
class AIReviewResult:
    issues: list[Any] = field(default_factory=list)
    chunk_meta: list[dict] = field(default_factory=list)


@dataclass
class ChunkMeta:
    chunk_index: int = 0
    chunk_size: int = 0
    cache_hit: bool = False


class ReportAggregator:
    def aggregate(self, issues) -> list[Any]:
        return list(issues or [])


@dataclass
class ReviewReport:
    issues: list[Any] = field(default_factory=list)


@dataclass
class DisplayIssue:
    payload: dict = field(default_factory=dict)


class EvaluationRunner:
    def run(self, issues) -> list[Any]:
        return list(issues or [])


@dataclass
class EvalResult:
    matched: int = 0


@dataclass
class EvalSuiteResult:
    results: list[EvalResult] = field(default_factory=list)


class DeterministicRuleEngine:
    def run(self, issues) -> list[Any]:
        return list(issues or [])
