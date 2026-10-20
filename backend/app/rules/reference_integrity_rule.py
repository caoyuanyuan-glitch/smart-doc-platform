from typing import Dict, List

from app.review_engine.reference_index import check_references, check_reference_style


class ReferenceIntegrityRule:
    """Authoritative figure/table reference check."""

    def check(self, full_text: str, visual_targets=None, parsed: bool = True) -> List[Dict]:
        return check_references(
            full_text,
            visual_targets=visual_targets,
            parsed=parsed,
            include_types=("figure", "table"),
        )

    def check_style(self, full_text: str, parsed: bool = True) -> List[Dict]:
        """引用写法规范：目标存在但写法为裸页码的情形。"""
        return check_reference_style(full_text, parsed=parsed)
