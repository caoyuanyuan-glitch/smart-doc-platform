from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from app.api import review as review_api
from app.database import OrphanReviewDataError, _prepare_review_fk_parents, collect_orphan_review_report
from app.review_engine.document_model import build_document_model
from app.review_engine.evidence import enrich_issue_evidence
from app.review_engine.issue_status import compute_status_counts
from app.review_engine.matching import rank_candidate
from app.review_engine.pairing import resolve_input_pairing
from app.review_engine.profile import apply_rule_gating, build_document_profile
from app.review_engine.reference_index import check_references
from app.review_engine.task_state import clear_task_state
from app.review_engine.visual import build_visual_verification, map_visual_status
from app.rules.reference_integrity_rule import ReferenceIntegrityRule
from app.services.chunker import create_smart_chunker


def test_chunker_keeps_all_chapters_without_sampling():
    text = "\n\n".join(f"第{index}章 标题{index}\n" + ("X" * 50) for index in range(1, 7))
    chunker = create_smart_chunker(max_chunks=3, max_chars=80, sampling_mode="off")
    chunks = chunker.chunk_document(text)
    assert len(chunks) >= 6
    assert chunker.last_diagnostics.get("skipped_chapters") in (None, [], "")


def test_chunker_even_sampling_skips_chapters_when_enabled():
    text = "\n\n".join(f"第{index}章 标题{index}\n" + ("Y" * 50) for index in range(1, 7))
    chunker = create_smart_chunker(max_chunks=3, max_chars=80, sampling_mode="even")
    chunks = chunker.chunk_document(text)
    assert len(chunks) <= 3
    skipped = chunker.last_diagnostics.get("skipped_chapters") or []
    assert skipped


def test_select_ai_audit_chunks_default_keeps_all(monkeypatch):
    monkeypatch.setenv("REVIEW_SAMPLING_MODE", "off")
    chunks = [(index, index, f"c{index}") for index in range(1, 6)]
    assert review_api._select_ai_audit_chunks(chunks, 2) == chunks


def test_pairing_modes_and_unpaired_does_not_merge():
    docx = SimpleNamespace(id=1, file_type="docx", filename="G99RS.docx", user_id=8)
    pdf_same = SimpleNamespace(id=2, file_type="pdf", filename="G99RS.pdf", user_id=8)
    pdf_other = SimpleNamespace(id=3, file_type="pdf", filename="WH-R02.pdf", user_id=8)
    only_docx = resolve_input_pairing(docx)
    only_pdf = resolve_input_pairing(SimpleNamespace(id=9, file_type="pdf", filename="a.pdf"))
    paired = resolve_input_pairing(docx, pdf_same)
    unpaired = resolve_input_pairing(docx, pdf_other)
    assert only_docx.input_mode == "B"
    assert only_pdf.input_mode == "C"
    assert paired.pairing_status == "paired"
    assert unpaired.pairing_status == "unpaired"
    assert unpaired.needs_user_confirm is True


def test_document_model_and_evidence_location():
    content = "第1章 概述\n请检查交户界面。\n"
    model = build_document_model(content, source_format="docx", document_language="zh-CN")
    issue = enrich_issue_evidence({"original_text": "交户界面", "status": "pending", "severity": "general"}, model)
    assert issue["evidence"]["location_quality"] == "verified"
    assert str(issue["position_object"]["chapter"]).startswith("第1章")
    assert issue["source_format"] == "docx"


def test_rule_gating_skips_english_only_on_chinese_profile():
    profile = build_document_profile("这是中文说明书内容" * 8, file_type="docx", language="zh")
    kept, diagnostics = apply_rule_gating(
        [{"rule": "ENG-CN-001", "status": "pending"}, {"rule": "CYY-CN-SPELL-007", "status": "pending"}],
        profile,
    )
    rules = {item["rule"] for item in kept}
    assert "ENG-CN-001" not in rules
    assert "CYY-CN-SPELL-007" in rules
    assert diagnostics["skipped_rule_issues"] == 1


def test_fuzzy_match_is_candidate_only():
    structure = rank_candidate("点击确定", "点击取消", rule_id="UI-001")
    assert structure.is_candidate is True
    assert structure.rejected_reason == "structure_mismatch"
    protected = rank_candidate("加入 10 ul 试剂", "加入 20 ul 试剂", rule_id="NUM-001")
    assert protected.is_candidate is True
    assert "numbers" in protected.protected_literal_diff
    assert protected.rejected_reason == "protected_literal_mismatch"


def test_reference_index_is_single_authority_for_figures():
    text = "请参见表 3。\n\n图 2 显示结果。\nSee Table 9 and Figure 8.\nSee Figure 100.\n"
    via_index = check_references(text)
    via_rule = ReferenceIntegrityRule().check(text)
    originals = {item["original_text"] for item in via_index}
    assert any("表" in item for item in originals)
    assert any("Figure" in item or "Table" in item for item in originals)
    assert {item["rule"] for item in via_index} == {item["rule"] for item in via_rule}
    assert all(item["rule"] != "REF-004" for item in via_index)


def test_reference_index_aggregates_when_too_many_missing():
    text = "\n".join(f"See Figure {index}." for index in range(1, 13))
    issues = check_references(text)
    assert any(item["rule"] == "REF-INDEX-001" for item in issues)
    assert all(item.get("target_status") != "target_not_found" or item["rule"] == "REF-INDEX-001" for item in issues)


def test_visual_not_required_and_status_counts():
    assert map_visual_status("not_required") == "not_required"
    issues = [
        {"status": "pending", "severity": "general", "visual_verification": build_visual_verification(status="not_required")},
        {"status": "blocked", "severity": "serious", "category": "引用完整性", "visual_verification": build_visual_verification(status="provider_unavailable")},
        {"status": "confirmed", "severity": "fatal", "visual_verification": build_visual_verification(status="verified")},
    ]
    counts = compute_status_counts(issues)
    assert counts["pending_count"] == 1
    assert counts["blocked_count"] == 1
    assert counts["confirmed_fatal"] == 1
    assert counts["visual_unverified_count"] == 1
    assert counts["reference_blocked_count"] == 1


def test_basis_trace_isolated_by_review_id():
    review_api._store_basis_trace(11, {"basis_source": "local", "review_id": 11})
    review_api._store_basis_trace(12, {"basis_source": "es", "review_id": 12})
    assert review_api._load_basis_trace(11)["basis_source"] == "local"
    assert review_api._load_basis_trace(12)["basis_source"] == "es"
    clear_task_state(11)
    review_api._review_observation_store.pop("11:basis_trace", None)
    assert review_api._load_basis_trace(12)["basis_source"] == "es"


def test_chunk_cache_key_excludes_review_id(monkeypatch):
    monkeypatch.setattr(review_api, "_review_cache_version", lambda: "v1")
    monkeypatch.setattr(review_api, "_ai_provider_cache_fingerprint", lambda: "p1")
    key_a = review_api._build_ai_chunk_cache_key("chunk", "cn", "basis", review_id=1)
    key_b = review_api._build_ai_chunk_cache_key("chunk", "cn", "basis", review_id=2)
    assert key_a == key_b


def test_orphan_fk_migration_aborts():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE documents (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE reviews (id INTEGER PRIMARY KEY, document_id INTEGER)"))
        conn.execute(text("INSERT INTO reviews (id, document_id) VALUES (1, 99)"))
        report = collect_orphan_review_report(conn)
        assert report["has_orphans"] is True
        assert report["recommendation"] == "abort_migration"
        with pytest.raises(OrphanReviewDataError):
            _prepare_review_fk_parents(conn)


def test_chunker_ten_chapters_and_coverage_ratio():
    text = "\n\n".join(f"第{index}章 标题{index}\n" + ("Z" * 40) for index in range(1, 11))
    chunker = create_smart_chunker(max_chunks=4, max_chars=80, sampling_mode="off")
    chunks = chunker.chunk_document(text)
    assert len(chunks) >= 10
    coverage = chunker.last_diagnostics
    assert coverage["coverage_ratio"] >= 0.99
    assert coverage["skipped_chunk_count"] == 0
    assert not coverage.get("skipped_chapters")


def test_figure_100_single_issue_from_both_entrypoints():
    text = "See Figure 100.\n"
    combined = ReferenceIntegrityRule().check(text) + review_api._run_cross_reference_audit(text)
    figure_issues = [item for item in combined if "100" in str(item.get("original_text") or "")]
    assert len(figure_issues) == 1


def test_figure_label_variants_share_index():
    text = "图100 标题\nSee Fig. 100 and Figure 100 and 图 100.\n"
    issues = check_references(text)
    assert issues == []


def test_visual_only_reference_is_blocked():
    issues = check_references("See Figure 2.", visual_targets={"figure": ["2"]}, parsed=True)
    assert issues
    assert issues[0]["target_status"] == "target_visual_only"
    assert issues[0]["status"] == "blocked"


def test_unparsed_reference_is_blocked():
    issues = check_references("See Figure 2.", parsed=False)
    assert issues
    assert issues[0]["target_status"] == "target_not_parsed"
    assert issues[0]["status"] == "blocked"


def test_coordinate_string_is_unverified_and_blocked():
    issue = enrich_issue_evidence({"original_text": "(12.3, 45.6)", "severity": "fatal", "status": "pending"}, None)
    assert issue["evidence"]["location_quality"] == "unverified"
    assert issue["status"] == "blocked"


def test_docx_evidence_not_overwritten_by_missing_pdf_page():
    model = build_document_model("第1章 概述\n交户界面已开启。\n", source_format="docx")
    issue = {
        "original_text": "交户界面",
        "status": "pending",
        "severity": "general",
        "position": {"page": 87, "source": "pdf_text_layer", "char_start": 999, "char_end": 1000},
    }
    enriched = enrich_issue_evidence(issue, model, source_format="docx")
    assert enriched["position_object"]["char_start"] != 999
    assert enriched["evidence"]["source_layer"] == "docx"
    assert str(enriched["position_object"]["chapter"]).startswith("第1章")


def test_cross_chunk_same_issue_merged_different_chapter_kept():
    same = [
        {"rule": "CYY-CN-SPELL-007", "category": "错别字", "chapter": "第1章", "original_text": "交户界面"},
        {"rule": "CYY-CN-SPELL-007", "category": "错别字", "chapter": "第1章", "original_text": "交户界面"},
    ]
    merged = review_api._dedup_across_chunks(same)
    assert len(merged) == 1
    assert merged[0]["dedupe_reason"] == "same_identity_key"
    different = [
        {"rule": "CYY-CN-SPELL-007", "category": "错别字", "chapter": "第1章", "original_text": "交户界面"},
        {"rule": "CYY-CN-SPELL-007", "category": "错别字", "chapter": "第2章", "original_text": "交户界面"},
    ]
    kept = review_api._dedup_across_chunks(different)
    assert len(kept) == 2


def test_cluster_keeps_different_chapters_separate():
    issues = [
        {"rule": "PUNCT-001", "category": "标点符号", "chapter": "第1章", "original_text": "，", "position": '{"start":1,"end":2}'},
        {"rule": "PUNCT-001", "category": "标点符号", "chapter": "第2章", "original_text": "，", "position": '{"start":10,"end":11}'},
    ]
    merged = review_api._cluster_merge_issues(issues)
    assert len(merged) == 2
