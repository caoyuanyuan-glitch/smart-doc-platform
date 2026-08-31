from typing import Dict, List

from app.review_engine.reference_index import check_references


class ReferenceIntegrityRule:
    """Authoritative figure/table reference check."""

    def check(self, full_text: str, visual_targets=None, parsed: bool = True) -> List[Dict]:
        return check_references(
            full_text,
            visual_targets=visual_targets,
            parsed=parsed,
            include_types=("figure", "table"),
        )
