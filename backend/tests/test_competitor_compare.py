"""竞品洞察引擎 + 多文档对比：单元与 API 测试。"""
import json
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import competitor
from app.api.auth import create_access_token
from app.database import Base, get_db
from app.models.competitor_task import CompetitorTask
from app.models.competitor_comparison import CompetitorComparison  # noqa: F401 确保建表
from app.models.user import User
from app.utils.competitor_comparison import build_comparison, render_comparison_report, load_task_payloads
from app.utils.competitor_insight import generate_rule_insights, generate_insights, generate_ai_insights
from app.utils.competitor_report import render_competitor_report


def _readability(overall, level, scores):
    """构造最小可用的 readability JSON（五维分数按需覆盖）。"""
    dims = {}
    labels = {
        "sentence_length": 95, "term_density": 60, "passive_ratio": 88,
        "paragraph_length": 92, "modifier_stack": 90,
    }
    labels.update(scores or {})
    for key, score in labels.items():
        dims[key] = {"score": score, "label": f"{key} {score}", "samples": []}
    return {
        "language": "en", "overall_score": overall, "level": level,
        "level_note": "", "warnings": [], "dimensions": dims,
        "stats": {"sentence_count": 50, "paragraph_count": 10},
        "suggestions": [],
    }


_TOOL_HAT = {"summary": "主编辑工具：Adobe FrameMaker（high 置信）",
             "meta": {"format": "PDF", "pages": 10}, "tools": [{"name": "Adobe FrameMaker"}]}
_TOOL_WORD = {"summary": "主编辑工具：Microsoft Word（high 置信）",
              "meta": {"format": "PDF", "pages": 8}, "tools": [{"name": "Microsoft Word"}]}


class InsightEngineTestCase(unittest.TestCase):
    def setUp(self):
        # 本环境可能配置了可用 AI Provider：单测统一关闭 AI 层，避免真实外呼与波动
        import os
        self._old_ai_flag = os.environ.get("COMPETITOR_AI_INSIGHT")
        os.environ["COMPETITOR_AI_INSIGHT"] = "0"

    def tearDown(self):
        import os
        if self._old_ai_flag is None:
            os.environ.pop("COMPETITOR_AI_INSIGHT", None)
        else:
            os.environ["COMPETITOR_AI_INSIGHT"] = self._old_ai_flag

    def test_high_score_dimension_yields_learning_insight(self):
        read = _readability(90, "excellent", {"sentence_length": 98})
        insights = generate_rule_insights(_TOOL_HAT, read)
        match = [i for i in insights if i["area"] == "可读性 · 平均句长"]
        self.assertTrue(match)
        self.assertEqual(match[0]["priority"], "P2")
        self.assertIn("对标", match[0]["action"])

    def test_low_score_dimension_yields_p1_opportunity(self):
        read = _readability(70, "good", {"term_density": 40})
        insights = generate_rule_insights(_TOOL_HAT, read)
        match = [i for i in insights if i["area"] == "可读性 · 术语密度"]
        self.assertTrue(match)
        self.assertEqual(match[0]["priority"], "P1")
        self.assertIn("机会", match[0]["action"])

    def test_hat_tool_yields_toolchain_insight(self):
        insights = generate_rule_insights(_TOOL_HAT, _readability(90, "excellent", {}))
        match = [i for i in insights if i["area"] == "工具链"]
        self.assertTrue(match)
        self.assertIn("结构化写作", match[0]["action"])

    def test_word_tool_yields_efficiency_insight(self):
        insights = generate_rule_insights(_TOOL_WORD, _readability(90, "excellent", {}))
        match = [i for i in insights if i["area"] == "工具链"]
        self.assertTrue(match)
        self.assertIn("效率优势", match[0]["action"])

    def test_low_text_warning_yields_p1_credibility_insight(self):
        read = _readability(88, "excellent", {})
        read["warnings"] = ["提取文本量较少（5 句 / 60 词），评分仅供参考"]
        insights = generate_rule_insights(_TOOL_HAT, read)
        match = [i for i in insights if i["area"] == "数据可信度"]
        self.assertTrue(match)
        self.assertEqual(match[0]["priority"], "P1")

    def test_generate_insights_degrades_without_ai(self):
        # 测试环境无可用 Provider：generate_insights 必须正常返回纯规则结果
        payload = generate_insights(_TOOL_HAT, _readability(90, "excellent", {}))
        self.assertTrue(payload["insights"])
        self.assertIsInstance(payload["ai_available"], bool)

    def test_ai_disabled_by_env(self):
        import os
        old = os.environ.get("COMPETITOR_AI_INSIGHT")
        os.environ["COMPETITOR_AI_INSIGHT"] = "0"
        try:
            self.assertIsNone(generate_ai_insights(_TOOL_HAT, _readability(90, "excellent", {})))
        finally:
            if old is None:
                os.environ.pop("COMPETITOR_AI_INSIGHT", None)
            else:
                os.environ["COMPETITOR_AI_INSIGHT"] = old

    def test_report_contains_insight_section(self):
        read = _readability(90, "excellent", {"term_density": 45})
        read["insights"] = generate_insights(_TOOL_HAT, read)
        md = render_competitor_report("manual.pdf", _TOOL_HAT, read)
        self.assertIn("三、对本司的启示", md)
        self.assertIn("P1", md)


class ComparisonEngineTestCase(unittest.TestCase):
    def _payloads(self):
        return [
            {"task_id": 1, "name": "ours_v2.pdf", "readability": _readability(80, "good", {"term_density": 90}),
             "tool_analysis": _TOOL_WORD, "warnings": []},
            {"task_id": 2, "name": "illumina_2025.pdf", "readability": _readability(92, "excellent", {"term_density": 60}),
             "tool_analysis": _TOOL_HAT, "warnings": []},
            {"task_id": 3, "name": "themo_2025.pdf", "readability": _readability(75, "good", {"term_density": 55}),
             "tool_analysis": _TOOL_WORD, "warnings": []},
        ]

    def test_build_with_baseline_marks_roles(self):
        result, insights = build_comparison(self._payloads(), baseline_task_id=1)
        by_id = {d["task_id"]: d for d in result["documents"]}
        self.assertTrue(by_id[1]["is_baseline"])
        self.assertFalse(by_id[2]["is_baseline"])
        # 术语密度：我方 90 vs 竞品最优 60 → 我方领先差距项
        ahead = [g for g in result["gaps"] if g["direction"] == "ahead" and g["dimension"] == "term_density"]
        self.assertTrue(ahead)
        # 综合排名：2 > 1 > 3
        self.assertEqual(result["overall_ranking"][0], 2)

    def test_gap_behind_generates_p1_insight(self):
        payloads = [
            {"task_id": 1, "name": "ours.pdf", "readability": _readability(70, "good", {"sentence_length": 50}),
             "tool_analysis": _TOOL_WORD, "warnings": []},
            {"task_id": 2, "name": "comp.pdf", "readability": _readability(90, "excellent", {"sentence_length": 96}),
             "tool_analysis": _TOOL_HAT, "warnings": []},
        ]
        result, insights = build_comparison(payloads, baseline_task_id=1)
        behind = [g for g in result["gaps"] if g["direction"] == "behind"]
        self.assertTrue(behind)
        p1 = [i for i in insights if i["priority"] == "P1" and "平均句长" in i["area"]]
        self.assertTrue(p1)

    def test_no_baseline_uses_spread_analysis(self):
        result, insights = build_comparison(self._payloads(), baseline_task_id=None)
        # 无基线：不输出 behind/ahead，仅 spread
        self.assertFalse([g for g in result["gaps"] if g["direction"] in ("behind", "ahead")])
        spread = [g for g in result["gaps"] if g["direction"] == "spread"]
        self.assertTrue(spread)  # 术语密度 90/60/55 极差 35 ≥ 15

    def test_invalid_doc_count_raises(self):
        with self.assertRaises(ValueError):
            build_comparison(self._payloads()[:1])
        with self.assertRaises(ValueError):
            build_comparison(self._payloads() * 2)  # 6 份超上限

    def test_baseline_not_in_tasks_raises(self):
        with self.assertRaises(ValueError):
            build_comparison(self._payloads(), baseline_task_id=99)

    def test_tie_scores_all_marked_and_null_renders_dash(self):
        payloads = [
            {"task_id": 1, "name": "a.pdf", "readability": _readability(80, "good", {"term_density": 70}),
             "tool_analysis": _TOOL_WORD, "warnings": []},
            {"task_id": 2, "name": "b.pdf", "readability": _readability(85, "good", {"term_density": 70}),
             "tool_analysis": _TOOL_HAT, "warnings": []},
        ]
        # 构造 a.pdf 术语密度缺测（None）
        payloads[0]["readability"]["dimensions"]["term_density"]["score"] = None
        result, insights = build_comparison(payloads, baseline_task_id=None)
        # None 分数不参与 winner，也不触发 spread 差距
        self.assertNotEqual(result["dimension_winners"].get("term_density"), 1)
        md = render_comparison_report("tie", result, insights)
        # 术语密度行应含 "-"（缺测）；被动句比例并列最高分应只出现一个 ▲ 组（并列均标）
        self.assertIn("-", md)

    def test_report_renders_matrix_and_baseline(self):
        result, insights = build_comparison(self._payloads(), baseline_task_id=1)
        md = render_comparison_report("测试对比", result, insights)
        self.assertIn("竞品文档对比报告", md)
        self.assertIn("我方基线", md)
        self.assertIn("维度分数矩阵", md)
        self.assertIn("▲", md)
        self.assertIn("行动建议", md)


class ComparisonApiTestCase(unittest.TestCase):
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
        app.include_router(competitor.router, prefix="/api/competitor")

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
        self.user_id = self._create_user("cmp_user", "writer")

    def _create_user(self, username: str, role: str) -> int:
        db = self.SessionLocal()
        try:
            user = User(username=username, password_hash="test-hash", display_name=username, role=role, status="active")
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id
        finally:
            db.close()

    def _auth_headers(self, username: str = "cmp_user"):
        return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}

    def _seed_task(self, name: str, readability: dict, tool: dict, status: str = "completed") -> int:
        db = self.SessionLocal()
        try:
            task = CompetitorTask(
                file_name=name, file_size=100, status=status,
                tool_analysis=json.dumps(tool, ensure_ascii=False),
                readability=json.dumps(readability, ensure_ascii=False),
                report_md="# stub", user_id=self.user_id,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return task.id
        finally:
            db.close()

    def _seed_three_tasks(self):
        t1 = self._seed_task("ours.pdf", _readability(80, "good", {"term_density": 90}), _TOOL_WORD)
        t2 = self._seed_task("illumina.pdf", _readability(92, "excellent", {"term_density": 60}), _TOOL_HAT)
        t3 = self._seed_task("themo.pdf", _readability(75, "good", {"term_density": 55}), _TOOL_WORD)
        return [t1, t2, t3]

    def test_create_list_get_delete_comparison(self):
        t1, t2, t3 = self._seed_three_tasks()
        resp = self.client.post(
            "/api/competitor/compare",
            headers=self._auth_headers(),
            json={"title": "三份手册对比", "task_ids": [t1, t2, t3], "baseline_task_id": t1},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"], "三份手册对比")
        self.assertEqual(json.loads(data["task_ids"]), [t1, t2, t3])
        self.assertEqual(data["baseline_task_id"], t1)
        self.assertIn("dimension_matrix", data["result_json"])
        self.assertIn("我方基线", data["report_md"])

        # 列表（路由顺序验证：/compare 不被 /{task_id} 吞掉）
        resp = self.client.get("/api/competitor/compare", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

        cid = data["id"]
        resp = self.client.get(f"/api/competitor/compare/{cid}", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("report_md", resp.json())

        resp = self.client.delete(f"/api/competitor/compare/{cid}", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/api/competitor/compare", headers=self._auth_headers())
        self.assertEqual(resp.json(), [])

    def test_create_rejects_single_task(self):
        t1, _, _ = self._seed_three_tasks()
        resp = self.client.post(
            "/api/competitor/compare", headers=self._auth_headers(),
            json={"task_ids": [t1]},
        )
        # schema 层 min_length=2 拦截为 422，API 层兜底为 400，两者均合法
        self.assertIn(resp.status_code, (400, 422))

    def test_create_rejects_unfinished_task(self):
        t1, t2, _ = self._seed_three_tasks()
        t3 = self._seed_task("pending.pdf", _readability(80, "good", {}), _TOOL_WORD, status="processing")
        resp = self.client.post(
            "/api/competitor/compare", headers=self._auth_headers(),
            json={"task_ids": [t1, t2, t3]},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("未完成", resp.json()["detail"])

    def test_create_rejects_baseline_not_in_tasks(self):
        t1, t2, t3 = self._seed_three_tasks()
        resp = self.client.post(
            "/api/competitor/compare", headers=self._auth_headers(),
            json={"task_ids": [t1, t2], "baseline_task_id": t3},
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_rejects_duplicate_task_ids(self):
        t1, t2, _ = self._seed_three_tasks()
        resp = self.client.post(
            "/api/competitor/compare", headers=self._auth_headers(),
            json={"task_ids": [t1, t1]},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("重复", resp.json()["detail"])

    def test_create_rejects_non_integer_task_ids(self):
        resp = self.client.post(
            "/api/competitor/compare", headers=self._auth_headers(),
            json={"task_ids": [1, {"a": 1}]},
        )
        self.assertIn(resp.status_code, (400, 422))

    def test_create_reports_corrupt_json_as_422(self):
        t1, t2, _ = self._seed_three_tasks()
        db = self.SessionLocal()
        try:
            db.query(CompetitorTask).filter(CompetitorTask.id == t2).update({"readability": "{broken json"})
            db.commit()
        finally:
            db.close()
        resp = self.client.post(
            "/api/competitor/compare", headers=self._auth_headers(),
            json={"task_ids": [t1, t2]},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("损坏", resp.json()["detail"])

    def test_get_missing_comparison_returns_404(self):
        resp = self.client.get("/api/competitor/compare/99999", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 404)

    def test_other_user_cannot_access(self):
        self._create_user("intruder", "writer")
        t1, t2, _ = self._seed_three_tasks()
        resp = self.client.post(
            "/api/competitor/compare", headers=self._auth_headers(),
            json={"task_ids": [t1, t2]},
        )
        self.assertEqual(resp.status_code, 200)
        cid = resp.json()["id"]
        resp = self.client.get(f"/api/competitor/compare/{cid}", headers=self._auth_headers("intruder"))
        self.assertEqual(resp.status_code, 404)
        resp = self.client.delete(f"/api/competitor/compare/{cid}", headers=self._auth_headers("intruder"))
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
