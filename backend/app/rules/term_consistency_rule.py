import re
from typing import Dict, List


class TermConsistencyRule:
    PAIRS = [
        ('Conversion Enzyme', ['converting enzyme']),
        ('Hamilton', ['HamiLton']),
        ('Well', ['WeLL']),
    ]

    def check(self, text: str) -> List[Dict]:
        issues = []
        content = str(text or '')
        for standard, variants in self.PAIRS:
            for variant in variants:
                for match in re.finditer(re.escape(variant), content):
                    issues.append({
                        'severity': 'general',
                        'category': '术语一致性',
                        'rule': 'TERM-CONSISTENCY-001',
                        'original_text': variant,
                        'suggestion': standard,
                        'description': f'术语不一致: "{variant}" 建议统一为 "{standard}"。',
                        'audit_basis': '术语一致性检查',
                        'confidence': 88,
                        'source': 'rule',
                        'position': f'{match.start()}-{match.end()}',
                    })
        return issues
