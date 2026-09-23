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


def test_paragraph_context_returns_full_paragraph_around_issue():
    paragraph = 'The reagent cartridge must stay upright. ' + ('Do not tilt it. ' * 25)
    content = 'Heading\n\nUnrelated intro line.\n\n' + paragraph + '\n\nNext section.'
    start = content.find('reagent cartridge')
    end = start + len('reagent cartridge')

    snippet = review_api._paragraph_context(content, start, end)

    assert 'reagent cartridge' in snippet
    assert 'Do not tilt it.' in snippet
    assert 'Next section.' not in snippet
    assert 'Unrelated intro line.' not in snippet


def test_paragraph_context_grows_past_short_paragraphs():
    content = '\n\n'.join(['cell-%d' % index for index in range(40)])
    start = content.find('cell-20')
    end = start + len('cell-20')

    snippet = review_api._paragraph_context(content, start, end, min_length=120)

    assert 'cell-20' in snippet
    assert len(snippet) >= 120
    assert 'cell-19' in snippet


def test_expand_issue_context_keeps_compare_mode_block():
    context = '主文档：alpha\n参考文档：beta'
    issue = SimpleNamespace(original_text='alpha', context=context, position='{}')

    review_api._expand_issue_context_for_display(issue, 'alpha in the main document')

    assert issue.context == context


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
