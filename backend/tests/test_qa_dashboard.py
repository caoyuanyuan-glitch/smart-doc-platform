from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import qa
from app.api.auth import get_current_user
from app.api.qa import BEIJING_TZ, _answer_success, _iter_beijing_dates, _to_utc_naive
from app.database import Base, get_db
from app.models.qa_history import QaMessage, QaSession
from app.models.user import User


class QaDashboardHelpersTest(unittest.TestCase):
    def test_beijing_midnight_converts_to_previous_utc_afternoon(self):
        dt = datetime(2026, 8, 29, 0, 0, 0, tzinfo=BEIJING_TZ)
        utc = _to_utc_naive(dt)
        self.assertEqual(utc, datetime(2026, 8, 28, 16, 0, 0))
        self.assertIsNone(utc.tzinfo)

    def test_answer_success_keeps_choose_prompt(self):
        self.assertFalse(_answer_success(""))
        self.assertFalse(_answer_success("官网未找到匹配的说明书"))
        self.assertFalse(_answer_success("当前知识范围内没有可用文档。"))
        self.assertTrue(_answer_success("根据说明书，开机步骤如下"))
        self.assertTrue(_answer_success("定位到 2 本说明书，请选择"))

    def test_iter_beijing_dates_includes_both_ends(self):
        start = datetime(2026, 8, 28, 10, 0, tzinfo=BEIJING_TZ)
        end = datetime(2026, 8, 30, 9, 0, tzinfo=BEIJING_TZ)
        self.assertEqual(list(_iter_beijing_dates(start, end)), [
            "2026-08-28", "2026-08-29", "2026-08-30",
        ])


class QaDashboardApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)
        cls.current_user = SimpleNamespace(id=1, role="admin", username="admin")

        app = FastAPI()
        app.include_router(qa.router, prefix="/api/qa")

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_user():
            return cls.current_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user
        cls.client = TestClient(app)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.__class__.current_user = SimpleNamespace(id=1, role="admin", username="admin")
        db = self.SessionLocal()
        try:
            db.add(User(username="admin", password_hash="x", display_name="管理员", role="admin", status="active"))
            db.commit()
        finally:
            db.close()

    def _add_turn(self, created_at, session_type="general", question="q", answer="ok", search_hit=1, user_id=1):
        db = self.SessionLocal()
        try:
            sess = QaSession(user_id=user_id, session_type=session_type, title=question, created_at=created_at, updated_at=created_at)
            db.add(sess)
            db.flush()
            db.add(QaMessage(session_id=sess.id, role="user", content=question, created_at=created_at))
            db.add(QaMessage(
                session_id=sess.id,
                role="assistant",
                content=answer,
                search_hit=search_hit,
                created_at=created_at + timedelta(seconds=1),
            ))
            db.commit()
        finally:
            db.close()

    def test_today_includes_beijing_early_morning_utc_yesterday(self):
        now_bj = datetime.now(BEIJING_TZ)
        today_start_utc = _to_utc_naive(datetime(now_bj.year, now_bj.month, now_bj.day, tzinfo=BEIJING_TZ))
        early_today = today_start_utc + timedelta(minutes=30)
        yesterday_noon = today_start_utc - timedelta(hours=12)
        self._add_turn(early_today, question="today-q", answer="today-a")
        self._add_turn(yesterday_noon, question="yest-q", answer="yest-a")

        today = self.client.get("/api/qa/dashboard", params={"period": "today"}).json()
        self.assertEqual(today["overview"]["conversations"], 1)
        self.assertEqual(today["total"], 1)
        self.assertEqual(today["items"][0]["question"], "today-q")
        self.assertEqual(len(today["charts"]["conversations"]), 1)

        yesterday = self.client.get("/api/qa/dashboard", params={"period": "yesterday"}).json()
        self.assertEqual(yesterday["overview"]["conversations"], 1)
        self.assertEqual(yesterday["total"], 1)
        self.assertEqual(yesterday["items"][0]["question"], "yest-q")

    def test_hit_rate_chart_keeps_both_session_types(self):
        now_utc = datetime.utcnow() - timedelta(seconds=10)
        self._add_turn(now_utc, session_type="general", question="kb", answer="kb-a", search_hit=1)
        self._add_turn(now_utc + timedelta(seconds=2), session_type="manual", question="man", answer="man-a", search_hit=0)

        data = self.client.get("/api/qa/dashboard", params={"period": "today"}).json()
        self.assertEqual(data["overview"]["conversations"], 2)
        self.assertEqual(data["charts"]["general_hit_rate"][-1]["rate"], 100.0)
        self.assertEqual(data["charts"]["manual_hit_rate"][-1]["rate"], 0.0)

    def test_regular_user_sees_overview_without_details(self):
        now_utc = datetime.utcnow() - timedelta(seconds=10)
        self._add_turn(now_utc, question="secret-q", answer="secret-a")
        self.__class__.current_user = SimpleNamespace(id=2, role="writer", username="writer")

        data = self.client.get("/api/qa/dashboard", params={"period": "today"}).json()
        self.assertEqual(data["overview"]["conversations"], 1)
        self.assertTrue(data["charts"]["conversations"])
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)
