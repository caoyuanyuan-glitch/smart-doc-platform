import json
import re
from typing import Dict, List, Tuple


class ReferenceIntegrityRule:
    @staticmethod
    def _encode_position(start: int, end: int, area: str = '正文') -> str:
        return json.dumps({'start': start, 'end': end, 'area': area}, ensure_ascii=False)

    @staticmethod
    def _is_heading_match(text: str, match: re.Match, label: str) -> bool:
        line_start = text.rfind('\n', 0, match.start()) + 1
        line_end = text.find('\n', match.start())
        if line_end < 0:
            line_end = len(text)
        line = text[line_start:line_end].strip()
        return bool(re.match(rf'^{label}\s+{match.group(1)}\b', line, re.IGNORECASE))

    def _collect_reference_matches(self, text: str, pattern: str, label: str) -> Tuple[set, Dict[str, re.Match]]:
        refs = set()
        positions: Dict[str, re.Match] = {}
        for match in re.finditer(pattern, text):
            if self._is_heading_match(text, match, label):
                continue
            ref_no = match.group(1)
            refs.add(ref_no)
            positions.setdefault(ref_no, match)
        return refs, positions

    def check(self, full_text: str) -> List[Dict]:
        issues = []
        text = str(full_text or '')

        ref_tables, table_positions = self._collect_reference_matches(text, r'\b[Tt]able\s+(\d+)\b', 'Table')
        ref_figures, figure_positions = self._collect_reference_matches(text, r'\b[Ff]igure\s+(\d+)\b', 'Figure')
        actual_tables = set(re.findall(r'^Table\s+(\d+)\b', text, re.MULTILINE))
        actual_figures = set(re.findall(r'^Figure\s+(\d+)\b', text, re.MULTILINE))

        for table_no in sorted(ref_tables - actual_tables, key=int):
            match = table_positions.get(table_no)
            issues.append({
                'severity': 'serious',
                'category': '引用完整性',
                'rule': 'REF-001',
                'original_text': f'Table {table_no}',
                'suggestion': f'建议补充 Table {table_no}，或删除该引用',
                'description': f'引用 Table {table_no}，但文档中未找到对应标题。',
                'audit_basis': '引用完整性检查',
                'confidence': 90,
                'source': 'rule',
                'position': self._encode_position(match.start(), match.end()) if match else '',
            })

        for figure_no in sorted(ref_figures - actual_figures, key=int):
            match = figure_positions.get(figure_no)
            issues.append({
                'severity': 'serious',
                'category': '引用完整性',
                'rule': 'REF-002',
                'original_text': f'Figure {figure_no}',
                'suggestion': f'建议补充 Figure {figure_no}，或删除该引用',
                'description': f'引用 Figure {figure_no}，但文档中未找到对应标题。',
                'audit_basis': '引用完整性检查',
                'confidence': 90,
                'source': 'rule',
                'position': self._encode_position(match.start(), match.end()) if match else '',
            })

        return issues
