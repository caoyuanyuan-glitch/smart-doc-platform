from types import SimpleNamespace

from app.api import review as review_api


def test_review_issues_for_display_keeps_false_positives():
    issues = [
        SimpleNamespace(status='pending', rule='TERM-001', original_text='alpha', context=''),
        SimpleNamespace(status='false_positive', rule='TERM-001', original_text='beta', context=''),
        SimpleNamespace(status='ignored', rule='TERM-001', original_text='gamma', context=''),
        SimpleNamespace(status='confirmed', rule='TERM-001', original_text='delta', context=''),
    ]

    visible = review_api._review_issues_for_display(issues)

    assert [issue.status for issue in visible] == ['pending', 'false_positive', 'confirmed']


def test_expand_issue_context_for_display_adds_surrounding_text():
    original = 'TARGET-PHRASE'
    content = ('left-' * 20) + original + ('-right' * 20)
    start = content.find(original)
    issue = SimpleNamespace(
        original_text=original,
        context=original,
        position=f'{{"start": {start}, "end": {start + len(original)}}}',
    )

    review_api._expand_issue_context_for_display(issue, content, radius=24)

    assert original in issue.context
    assert len(issue.context) > len(original)
    assert 'left-' in issue.context
    assert '-right' in issue.context


def test_extract_issue_snippet_keeps_longer_context():
    original = 'TARGET-PHRASE'
    content = ('alpha ' * 40) + original + (' beta' * 40)
    start = content.find(original)
    issue = {
        'original_text': original,
        'context': original,
        'position': f'{{"start": {start}, "end": {start + len(original)}}}',
    }

    snippet = review_api._extract_issue_snippet(issue, content)

    assert original in snippet
    assert len(snippet) > 80


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *args, **kwargs):
        return _FakeQuery(self.rows)


def test_judgment_stats_map_counts_false_positives_and_manual():
    db = _FakeDB([
        (7, 'confirmed', 'ai'),
        (7, 'false_positive', 'rule'),
        (7, 'pending', 'manual'),
        (7, 'ignored', 'ai'),
    ])

    stats = review_api._judgment_stats_map(db, [7])

    assert stats[7]['confirmed'] == 1
    assert stats[7]['false_positive'] == 1
    assert stats[7]['pending'] == 1
    assert stats[7]['manual'] == 1
