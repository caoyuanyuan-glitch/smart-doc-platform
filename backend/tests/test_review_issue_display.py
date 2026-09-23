from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import review as review_api
from app.api.auth import create_access_token
from app.database import Base, get_db
from app.models.document import Document
from app.models.issue import Issue
from app.models.review import Review
from app.models.user import User


def test_review_issues_for_display_keeps_false_positives():
    issues = [
        SimpleNamespace(status='pending', rule='TERM-001', original_text='alpha', context=''),
        SimpleNamespace(status='false_positive', rule='TERM-001', original_text='beta', context=''),
        SimpleNamespace(status='ignored', rule='TERM-001', original_text='gamma', context=''),
        SimpleNamespace(status='confirmed', rule='TERM-001', original_text='delta', context=''),
    ]

    visible = review_api._review_issues_for_display(issues)

    assert [issue.status for issue in visible] == ['pending', 'false_positive', 'confirmed']


def test_visible_review_issues_drops_judged_false_positives():
    issues = [
        SimpleNamespace(status='pending', rule='TERM-001', original_text='alpha', context=''),
        SimpleNamespace(status='false_positive', rule='TERM-001', original_text='beta', context=''),
        SimpleNamespace(status='ignored', rule='TERM-001', original_text='gamma', context=''),
        SimpleNamespace(status='confirmed', rule='TERM-001', original_text='delta', context=''),
    ]

    visible = review_api._visible_review_issues(issues)

    assert [issue.original_text for issue in visible] == ['alpha', 'delta']


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


class ReviewReportFalsePositiveTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

        app = FastAPI()
        app.include_router(review_api.router, prefix="/api/review")

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.review_id = self._seed_review_with_judged_issue()
        token = create_access_token({"sub": "report_admin"})
        self.headers = {"Authorization": f"Bearer {token}"}

    def _seed_review_with_judged_issue(self) -> int:
        db = self.SessionLocal()
        try:
            user = User(
                username="report_admin",
                password_hash="test-hash",
                display_name="report_admin",
                role="admin",
                status="active",
            )
            db.add(user)
            db.flush()

            # Keep the two markers far apart so the report context window of one
            # cannot accidentally contain the other marker.
            filler = " ".join(["filler"] * 200)
            content = (
                "REALMARKERTOKEN appears in the body. "
                + filler
                + " FALSEMARKERTOKEN is judged as a false positive."
            )
            document = Document(
                filename="report-demo.pdf",
                file_type="pdf",
                file_size=len(content),
                content=content,
                status="ready",
                preview="demo",
                user_id=user.id,
            )
            db.add(document)
            db.flush()

            review_row = Review(
                document_id=document.id,
                mode="hybrid",
                provider="deepseek",
                status="completed",
                total_issues=2,
                summary="{}",
            )
            db.add(review_row)
            db.flush()

            for severity, rule, original, status in (
                ("general", "TERM-001", "REALMARKERTOKEN", "pending"),
                ("general", "TERM-001", "FALSEMARKERTOKEN", "false_positive"),
            ):
                start = content.find(original)
                db.add(Issue(
                    review_id=review_row.id,
                    severity=severity,
                    category="术语一致性",
                    rule=rule,
                    chapter="1.1",
                    original_text=original,
                    context=content,
                    suggestion=original.replace("TOKEN", "-TERM"),
                    description="术语表述前后不一致，建议统一。",
                    audit_basis="英文技术文档术语一致性规范",
                    confidence=90,
                    source="rule",
                    status=status,
                    position=f'{{"start": {start}, "end": {start + len(original)}}}',
                ))
            db.commit()
            return review_row.id
        finally:
            db.close()

    def test_issue_list_keeps_false_positives_for_manual_review(self):
        response = self.client.get(f"/api/review/{self.review_id}/issues", headers=self.headers)

        assert response.status_code == 200
        originals = {issue["original_text"] for issue in response.json()}
        assert {"REALMARKERTOKEN", "FALSEMARKERTOKEN"} <= originals

    def test_reports_and_exports_exclude_judged_false_positives(self):
        for path in ("report", "export-html"):
            response = self.client.get(f"/api/review/{self.review_id}/{path}", headers=self.headers)
            assert response.status_code == 200, path
            assert "REALMARKERTOKEN" in response.text, path
            assert "FALSEMARKERTOKEN" not in response.text, path

        aggregated = self.client.get(f"/api/review/{self.review_id}/aggregated-report", headers=self.headers)
        assert aggregated.status_code == 200
        originals = {issue["original_text"] for issue in aggregated.json()["issues"]}
        assert "REALMARKERTOKEN" in originals
        assert "FALSEMARKERTOKEN" not in originals
