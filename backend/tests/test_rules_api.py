"""规则库导入/导出接口回归。

覆盖三个已修复的问题：
1. static 路径 /export 必须注册在 /{rule_id} 之前，否则被当作 rule_id 解析失败；
2. 导出需包含 severity/language，且不因默认分页被截断；
3. 导入为 JSON 数组（与导出格式一致），重复 rule_no 需跳过而不是报错。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import require_admin
from app.database import Base, get_db
from app.main import app
from app.models.rule import Rule as RuleModel


@pytest.fixture()
def client():
    # StaticPool：TestClient 的请求跑在独立线程，内存库需共享同一连接，
    # 否则每个线程会各自新建一个空库。
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: {"username": "admin", "role": "admin"}
    try:
        yield TestClient(app), session_local
    finally:
        app.dependency_overrides.clear()


def test_export_route_is_registered_before_dynamic_rule_id():
    paths = [route.path for route in app.routes if getattr(route, "path", "").startswith("/api/rules")]
    assert paths.index("/api/rules/export") < paths.index("/api/rules/{rule_id}")


def test_export_rules_returns_library_with_severity_and_language(client):
    test_client, session_local = client
    db = session_local()
    try:
        db.add(RuleModel(
            rule_no="EXT-T001", category="拼写", description="示例规则", regex=r"\bteh\b",
            example="teh", suggestion="the", audit_basis="依据",
            severity="serious", language="en",
        ))
        db.commit()
    finally:
        db.close()

    response = test_client.get("/api/rules/export")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["rule_no"] == "EXT-T001"
    assert payload[0]["severity"] == "serious"
    assert payload[0]["language"] == "en"


def test_export_rules_is_not_truncated_by_default_page_limit(client):
    test_client, session_local = client
    db = session_local()
    try:
        db.add_all([
            RuleModel(rule_no=f"EXT-B{i:03d}", category="拼写", description="d", regex="r")
            for i in range(120)
        ])
        db.commit()
    finally:
        db.close()

    response = test_client.get("/api/rules/export")

    assert response.status_code == 200
    assert len(response.json()) == 120


def test_dynamic_rule_id_route_still_resolves_after_reordering(client):
    test_client, session_local = client
    db = session_local()
    try:
        rule = RuleModel(
            rule_no="EXT-T002", category="拼写", description="d", regex="r",
            example="", suggestion="", audit_basis="",
        )
        db.add(rule)
        db.commit()
        rule_id = rule.id
    finally:
        db.close()

    response = test_client.get(f"/api/rules/{rule_id}")

    assert response.status_code == 200
    assert response.json()["rule_no"] == "EXT-T002"


def test_bulk_import_rules_skips_existing_and_in_batch_duplicates(client):
    test_client, session_local = client
    db = session_local()
    try:
        db.add(RuleModel(rule_no="R-DUP", category="拼写", description="已存在", regex="r"))
        db.commit()
    finally:
        db.close()

    payload = [
        {"rule_no": "R-NEW", "category": "拼写", "description": "新增", "regex": "r"},
        {"rule_no": "R-DUP", "category": "拼写", "description": "库中已存在", "regex": "r"},
        {"rule_no": "R-NEW", "category": "拼写", "description": "同批重复", "regex": "r"},
    ]

    response = test_client.post("/api/rules/bulk", json=payload)

    assert response.status_code == 200
    assert response.json()["created"] == 1
    assert response.json()["total"] == 3

    exported = {item["rule_no"] for item in test_client.get("/api/rules/export").json()}
    assert exported == {"R-DUP", "R-NEW"}


def test_bulk_import_rejects_multipart_upload(client):
    test_client, _ = client

    response = test_client.post(
        "/api/rules/bulk",
        files={"file": ("rules.json", b'[{"rule_no":"R1"}]', "application/json")},
    )

    # 前端改为读取文件后提交 JSON，接口本身只接受 JSON 数组。
    assert response.status_code == 422
