from dataclasses import dataclass, field
from typing import Any


@dataclass
class CandidateIssue:
    source: str = "rule"
    rule: str = ""
    category: str = ""
    severity: str = "general"
    original_text: str = ""
    suggestion: str = ""
    description: str = ""
    audit_basis: str = ""
    confidence: int = 0
    position: str = ""
    chapter: str = ""
    context: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "CandidateIssue":
        known = {field.name for field in cls.__dataclass_fields__.values() if field.name != "extras"}
        values = {key: data.get(key, "") for key in known}
        values["extras"] = {key: value for key, value in data.items() if key not in known}
        return cls(**values)

    def to_mapping(self) -> dict[str, Any]:
        data = {
            "source": self.source,
            "rule": self.rule,
            "category": self.category,
            "severity": self.severity,
            "original_text": self.original_text,
            "suggestion": self.suggestion,
            "description": self.description,
            "audit_basis": self.audit_basis,
            "confidence": self.confidence,
            "position": self.position,
            "chapter": self.chapter,
            "context": self.context,
        }
        data.update(self.extras)
        return data


@dataclass
class ValidationResult:
    accepted: bool
    reason: str = ""


@dataclass
class ReviewStageDiagnostics:
    stage: str
    input_count: int = 0
    output_count: int = 0
    dropped_count: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)
