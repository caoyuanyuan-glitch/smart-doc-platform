"""Review engine — composable pipeline for document quality review.

Architecture
------------
The engine decomposes the monolithic review flow into discrete stages:
1. DocumentContext  — cleaned text + chapter/offset indexing
2. Deterministic rules  — regex/structural checks (unit, date, URL, model…)
3. AI candidate discovery  — LLM-powered deep review
4. Issue validation  — evidence check, noop filter, sensitive entity guard
5. Dedup + aggregation  — pipeline.select_review_issues()
6. Persistence  — save to DB with stage diagnostics

Each stage is independently testable and contributes diagnostics
(input/output/dropped counts + duration) to the Review.summary JSON.

Compatibility
-------------
- Current ``review.py`` routes continue to call the original entry points.
- New engine modules are additive — they do not change existing API
  behaviour unless explicitly enabled (e.g. via ``REVIEW_USE_ORCHESTRATOR``).
- Migration happens gradually: deterministic rules move from inline code
  to ``rules/`` modules one group at a time.

Modules
-------
- ``context.py``         — DocumentContext builder
- ``models.py``          — CandidateIssue, ValidationResult, StageDiagnostics
- ``layers.py``          — Issue layer classification (deterministic/structural/AI)
- ``validation.py``      — AI issue evidence + safety checks
- ``pipeline.py``        — Issue ranking, de-duplication, shadow suppression
- ``orchestrator.py``    — Stage-based pipeline runner with diagnostics
- ``ai_candidates.py``   — AI candidate engine (chunking, provider, caching)
- ``reporting.py``       — Report aggregator (display groups, quality scoring)
- ``evaluation.py``      — Evaluation runner (baseline matching, consistency)
- ``annotation_baseline.py`` — Human review baseline parsing & evaluation
- ``rules/``             — Deterministic rule implementations (incremental)
"""

from importlib import import_module

from app.review_engine.models import CandidateIssue, ReviewStageDiagnostics, ValidationResult  # noqa: F401


def _optional_import(module_name, *symbols):
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        missing_name = exc.name or ""
        if missing_name != module_name and not module_name.startswith(missing_name + "."):
            raise
        return (None,) * len(symbols)
    return tuple(getattr(module, symbol) for symbol in symbols)


DocumentContext, TextSpan = _optional_import(
    "app.review_engine.context",
    "DocumentContext",
    "TextSpan",
)
ReviewOrchestrator, ReviewRunResult = _optional_import(
    "app.review_engine.orchestrator",
    "ReviewOrchestrator",
    "ReviewRunResult",
)
AICandidateEngine, AIReviewResult, ChunkMeta = _optional_import(
    "app.review_engine.ai_candidates",
    "AICandidateEngine",
    "AIReviewResult",
    "ChunkMeta",
)
ReportAggregator, ReviewReport, DisplayIssue = _optional_import(
    "app.review_engine.reporting",
    "ReportAggregator",
    "ReviewReport",
    "DisplayIssue",
)
EvaluationRunner, EvalResult, EvalSuiteResult = _optional_import(
    "app.review_engine.evaluation",
    "EvaluationRunner",
    "EvalResult",
    "EvalSuiteResult",
)
(DeterministicRuleEngine,) = _optional_import(
    "app.review_engine.rules.engine",
    "DeterministicRuleEngine",
)
