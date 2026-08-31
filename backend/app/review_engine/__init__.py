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
- New engine modules are additive and keep existing API behaviour stable.
- Migration happens gradually: deterministic rules move from inline code
  to ``rules/`` modules one group at a time.

Modules
-------
- ``context.py``         — DocumentContext builder
- ``models.py``          — CandidateIssue, ValidationResult, StageDiagnostics
- ``layers.py``          — Issue layer classification (deterministic/structural/AI)
- ``validation.py``      — AI issue evidence + safety checks
- ``pipeline.py``        — Issue ranking, de-duplication, shadow suppression
 - ``false_positives.py`` — Rulebook v1 false-positive matchers for default filtering
- ``orchestrator.py``    — Stage-based pipeline runner with diagnostics
- ``ai_candidates.py``   — AI candidate engine (chunking, provider, caching)
- ``reporting.py``       — Report aggregator (display groups, quality scoring)
- ``evaluation.py``      — Evaluation runner (baseline matching, consistency)
- ``annotation_baseline.py`` — Human review baseline parsing & evaluation
- ``rules/``             — Deterministic rule implementations (incremental)
"""

from app.review_engine.models import CandidateIssue, ReviewStageDiagnostics, ValidationResult  # noqa: F401
from app.review_engine.false_positives import is_rulebook_false_positive, rulebook_false_positive_reason  # noqa: F401

DocumentContext = None
TextSpan = None
ReviewOrchestrator = None
ReviewRunResult = None
AICandidateEngine = None
AIReviewResult = None
ChunkMeta = None
ReportAggregator = None
ReviewReport = None
DisplayIssue = None
EvaluationRunner = None
EvalResult = None
EvalSuiteResult = None
DeterministicRuleEngine = None
