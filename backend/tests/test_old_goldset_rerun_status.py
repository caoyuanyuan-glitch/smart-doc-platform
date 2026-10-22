"""R2: old goldset rerun must emit four explicit statuses, never generic skipped."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "g99_eval"))

from eval_common import (  # noqa: E402
    classify_old_goldset_status,
    expected_pdf_path,
    pdfs_for_goldset,
    redact_database_dsn,
)


def test_classify_rerun_when_review_row_and_baseline_exist():
    status, error = classify_old_goldset_status(
        baseline_exists=True,
        review_id=23,
        db_error=None,
        review_found=True,
        pdf_hits=[],
        expected_pdf="/tmp/missing.pdf",
    )
    assert status == "rerun"
    assert error is None


def test_classify_db_unavailable():
    status, error = classify_old_goldset_status(
        baseline_exists=True,
        review_id=23,
        db_error="OperationalError: dsn=sqlite:////tmp/app.db",
        review_found=False,
        pdf_hits=["/tmp/e25.pdf"],
        expected_pdf="/tmp/e25.pdf",
    )
    assert status == "db_unavailable"
    assert "OperationalError" in error


def test_classify_missing_pdf_when_never_reviewed():
    expected = expected_pdf_path("e25rs_en", Path("/data"))
    status, error = classify_old_goldset_status(
        baseline_exists=True,
        review_id=None,
        db_error=None,
        review_found=False,
        pdf_hits=[],
        expected_pdf=expected,
    )
    assert status == "missing_pdf"
    assert error == expected


def test_classify_no_review_id_when_pdf_exists():
    status, error = classify_old_goldset_status(
        baseline_exists=True,
        review_id=None,
        db_error=None,
        review_found=False,
        pdf_hits=["/data/e25rs_en.pdf"],
        expected_pdf="/data/**/*e25rs_en*.pdf",
    )
    assert status == "no_review_id"
    assert error is None


def test_pdfs_for_goldset_filters_by_name():
    hits = [
        "/data/GoSpatial_v2.pdf",
        "/data/e25rs_en.pdf",
        "/data/g99_noannot.pdf",
    ]
    assert pdfs_for_goldset("e25rs_en", hits) == ["/data/e25rs_en.pdf"]
    assert pdfs_for_goldset("gospatial_v2_24_en", hits) == ["/data/GoSpatial_v2.pdf"]
    assert pdfs_for_goldset("g99_v9_observed", hits) == ["/data/g99_noannot.pdf"]


def test_redact_database_dsn_hides_password():
    assert redact_database_dsn("postgresql://user:secret@localhost/db") == "postgresql://user:***@localhost/db"
    assert redact_database_dsn("sqlite:////tmp/app.db") == "sqlite:////tmp/app.db"
