from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from app.utils.runtime_config import bootstrap_runtime_env
from app.utils.runtime_paths import ensure_runtime_db_path

bootstrap_runtime_env()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ensure_runtime_db_path()}")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class ReviewForeignKeyError(RuntimeError):
    """Raised when review-module foreign keys cannot be applied."""


class OrphanReviewDataError(ReviewForeignKeyError):
    """Raised when orphan review rows would require silent rewrite."""

    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report or {}


_DELETED_DOCUMENT_FILENAME = "__deleted_document__"


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _ensure_legacy_sqlite_columns():
    """为旧版 SQLite 数据库补齐当前代码依赖的列。"""
    inspector = inspect(engine)

    try:
        document_columns = {col['name'] for col in inspector.get_columns('documents')}
    except Exception:
        document_columns = set()

    if document_columns and 'file_size' not in document_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE documents ADD COLUMN file_size BIGINT DEFAULT 0"))
    if document_columns and 'deleted_at' not in document_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE documents ADD COLUMN deleted_at DATETIME"))

    try:
        rule_columns = {col['name'] for col in inspector.get_columns('rules')}
    except Exception:
        rule_columns = set()

    if rule_columns and 'language' not in rule_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE rules ADD COLUMN language VARCHAR DEFAULT 'both'"))
    if rule_columns and 'severity' not in rule_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE rules ADD COLUMN severity VARCHAR DEFAULT 'general'"))

    try:
        review_columns = {col['name'] for col in inspector.get_columns('reviews')}
    except Exception:
        review_columns = set()

    if review_columns and 'completed_at' not in review_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE reviews ADD COLUMN completed_at DATETIME"))
    if review_columns and 'provider' not in review_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE reviews ADD COLUMN provider VARCHAR"))
    review_extra = {
        'stage': "ALTER TABLE reviews ADD COLUMN stage VARCHAR DEFAULT ''",
        'progress': "ALTER TABLE reviews ADD COLUMN progress INTEGER DEFAULT 0",
        'message': "ALTER TABLE reviews ADD COLUMN message TEXT DEFAULT ''",
        'heartbeat_at': "ALTER TABLE reviews ADD COLUMN heartbeat_at DATETIME",
        'error_message': "ALTER TABLE reviews ADD COLUMN error_message TEXT",
        'retry_count': "ALTER TABLE reviews ADD COLUMN retry_count INTEGER DEFAULT 0",
        'worker_id': "ALTER TABLE reviews ADD COLUMN worker_id VARCHAR",
        'started_at': "ALTER TABLE reviews ADD COLUMN started_at DATETIME",
        'filter_mode': "ALTER TABLE reviews ADD COLUMN filter_mode VARCHAR DEFAULT 'pipeline'",
    }
    for column_name, stmt in review_extra.items():
        if review_columns and column_name not in review_columns:
            with engine.begin() as conn:
                conn.execute(text(stmt))

    try:
        issue_columns = {col['name'] for col in inspector.get_columns('issues')}
    except Exception:
        issue_columns = set()

    if issue_columns and 'providers' not in issue_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE issues ADD COLUMN providers TEXT"))

    try:
        compare_columns = {col['name'] for col in inspector.get_columns('compare_tasks')}
    except Exception:
        compare_columns = set()

    if compare_columns and 'group_id' not in compare_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE compare_tasks ADD COLUMN group_id INTEGER"))
    if compare_columns and 'file_names' not in compare_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE compare_tasks ADD COLUMN file_names TEXT"))
    if compare_columns and 'task_type' not in compare_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE compare_tasks ADD COLUMN task_type VARCHAR DEFAULT 'doc'"))

    try:
        competitor_columns = {col['name'] for col in inspector.get_columns('competitor_tasks')}
    except Exception:
        competitor_columns = set()

    if competitor_columns and 'source_type' not in competitor_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE competitor_tasks ADD COLUMN source_type VARCHAR DEFAULT 'file'"))
    if competitor_columns and 'overall_score' not in competitor_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE competitor_tasks ADD COLUMN overall_score FLOAT DEFAULT 0.0"))
    if competitor_columns and 'experience' not in competitor_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE competitor_tasks ADD COLUMN experience TEXT"))

    try:
        translation_doc_columns = {col['name'] for col in inspector.get_columns('translation_docs')}
    except Exception:
        translation_doc_columns = set()

    if translation_doc_columns and 'source_char_count' not in translation_doc_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN source_char_count INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN ai_char_count INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN memory_char_count INTEGER DEFAULT 0"))

    if translation_doc_columns and 'batch_id' not in translation_doc_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN batch_id VARCHAR DEFAULT ''"))

    if translation_doc_columns and 'source_word_count' not in translation_doc_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN source_word_count INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN ai_word_count INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN memory_word_count INTEGER DEFAULT 0"))

    if translation_doc_columns and 'user_id' not in translation_doc_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN user_id INTEGER"))

    try:
        convert_task_columns = {col['name'] for col in inspector.get_columns('convert_tasks')}
    except Exception:
        convert_task_columns = set()

    if convert_task_columns and 'user_id' not in convert_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE convert_tasks ADD COLUMN user_id INTEGER"))

    try:
        plr_columns = {col['name'] for col in inspector.get_columns('polish_learning_rules')}
    except Exception:
        plr_columns = set()

    if plr_columns:
        stmts = []
        if 'rule_name' not in plr_columns:
            stmts.append("ALTER TABLE polish_learning_rules ADD COLUMN rule_name VARCHAR(128)")
        if 'engine_key' not in plr_columns:
            stmts.append("ALTER TABLE polish_learning_rules ADD COLUMN engine_key VARCHAR(64)")
        if 'description' not in plr_columns:
            stmts.append("ALTER TABLE polish_learning_rules ADD COLUMN description TEXT")
        if stmts:
            with engine.begin() as conn:
                for s in stmts:
                    conn.execute(text(s))

    try:
        qa_msg_columns = {col['name'] for col in inspector.get_columns('qa_messages')}
    except Exception:
        qa_msg_columns = set()

    if qa_msg_columns:
        stmts = []
        if 'search_hit' not in qa_msg_columns:
            stmts.append("ALTER TABLE qa_messages ADD COLUMN search_hit INTEGER DEFAULT 0")
        if 'relevance_score' not in qa_msg_columns:
            stmts.append("ALTER TABLE qa_messages ADD COLUMN relevance_score FLOAT DEFAULT 0.0")
        if stmts:
            with engine.begin() as conn:
                for s in stmts:
                    conn.execute(text(s))

    try:
        polish_feedback_columns = {col['name'] for col in inspector.get_columns('polish_feedback')}
    except Exception:
        polish_feedback_columns = set()

    if polish_feedback_columns:
        stmts = []
        if 'correction_items' not in polish_feedback_columns:
            stmts.append("ALTER TABLE polish_feedback ADD COLUMN correction_items TEXT")
        if 'polish_session_id' not in polish_feedback_columns:
            stmts.append("ALTER TABLE polish_feedback ADD COLUMN polish_session_id VARCHAR(64)")
        if stmts:
            with engine.begin() as conn:
                for s in stmts:
                    conn.execute(text(s))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_polish_feedback_polish_session_id ON polish_feedback (polish_session_id)"))


def _sqlite_has_fk(inspector, table_name, column_name, referred_table):
    try:
        fks = inspector.get_foreign_keys(table_name)
    except Exception:
        return False
    for fk in fks:
        if fk.get("referred_table") == referred_table and list(fk.get("constrained_columns") or []) == [column_name]:
            return True
    return False


def _table_columns(conn, table_name):
    return [row[1] for row in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()]


def _ensure_deleted_document_placeholder(conn):
    row = conn.execute(
        text("SELECT id FROM documents WHERE filename = :name LIMIT 1"),
        {"name": _DELETED_DOCUMENT_FILENAME},
    ).fetchone()
    if row:
        return row[0]
    columns = set(_table_columns(conn, "documents"))
    fields = ["filename"]
    values = [":name"]
    params = {"name": _DELETED_DOCUMENT_FILENAME}
    if "file_type" in columns:
        fields.append("file_type")
        values.append("'unknown'")
    if "file_size" in columns:
        fields.append("file_size")
        values.append("0")
    if "content" in columns:
        fields.append("content")
        values.append("''")
    if "status" in columns:
        fields.append("status")
        values.append("'deleted'")
    if "deleted_at" in columns:
        fields.append("deleted_at")
        values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(f"INSERT INTO documents ({', '.join(fields)}) VALUES ({', '.join(values)})"),
        params,
    )
    row = conn.execute(
        text("SELECT id FROM documents WHERE filename = :name LIMIT 1"),
        {"name": _DELETED_DOCUMENT_FILENAME},
    ).fetchone()
    return row[0]


def collect_orphan_review_report(conn) -> dict:
    tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
    orphan_reviews = []
    orphan_issues = []
    orphan_traces = []
    if "reviews" in tables:
        rows = conn.execute(
            text(
                "SELECT id, document_id FROM reviews "
                "WHERE document_id IS NULL OR document_id NOT IN (SELECT id FROM documents)"
            )
        ).fetchall()
        orphan_reviews = [{"id": row[0], "document_id": row[1], "suggestion": "abort_migration"} for row in rows]
    if "issues" in tables:
        rows = conn.execute(
            text(
                "SELECT id, review_id FROM issues "
                "WHERE review_id IS NULL OR review_id NOT IN (SELECT id FROM reviews)"
            )
        ).fetchall()
        orphan_issues = [{"id": row[0], "review_id": row[1], "suggestion": "abort_migration"} for row in rows]
    if "audit_traces" in tables:
        rows = conn.execute(
            text(
                "SELECT id, review_id FROM audit_traces "
                "WHERE review_id IS NULL OR review_id NOT IN (SELECT id FROM reviews)"
            )
        ).fetchall()
        orphan_traces = [{"id": row[0], "review_id": row[1], "suggestion": "abort_migration"} for row in rows]
    counts = {
        "orphan_reviews": len(orphan_reviews),
        "orphan_issues": len(orphan_issues),
        "orphan_traces": len(orphan_traces),
    }
    return {
        "has_orphans": any(counts.values()),
        "counts": counts,
        "orphan_reviews": orphan_reviews,
        "orphan_issues": orphan_issues,
        "orphan_traces": orphan_traces,
        "summary": counts,
        "recommendation": "abort_migration" if any(counts.values()) else "continue",
    }


def _prepare_review_fk_parents(conn):
    report = collect_orphan_review_report(conn)
    if report.get("has_orphans"):
        raise OrphanReviewDataError(
            "orphan review data blocks FK migration: " + str(report.get("summary") or report),
            report=report,
        )


def _rebuild_sqlite_table_with_fk(conn, table):
    from sqlalchemy.schema import CreateTable

    tmp_name = f"{table.name}__fk_mig"
    conn.execute(text(f"ALTER TABLE {table.name} RENAME TO {tmp_name}"))
    for idx in conn.execute(text(f"PRAGMA index_list({tmp_name})")).fetchall():
        name = idx[1]
        if name and not str(name).startswith("sqlite_autoindex"):
            conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
    conn.execute(CreateTable(table))
    old_cols = set(_table_columns(conn, tmp_name))
    shared = [column.name for column in table.columns if column.name in old_cols]
    col_sql = ", ".join(shared)
    conn.execute(text(f"INSERT INTO {table.name} ({col_sql}) SELECT {col_sql} FROM {tmp_name}"))
    conn.execute(text(f"DROP TABLE {tmp_name}"))


def _ensure_review_foreign_keys():
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    needed = []
    if "reviews" in tables and not _sqlite_has_fk(inspector, "reviews", "document_id", "documents"):
        needed.append("reviews")
    if "issues" in tables and not _sqlite_has_fk(inspector, "issues", "review_id", "reviews"):
        needed.append("issues")
    if "audit_traces" in tables and not _sqlite_has_fk(inspector, "audit_traces", "review_id", "reviews"):
        needed.append("audit_traces")
    if not needed:
        return
    from app.models.audit_trace import AuditTrace
    from app.models.issue import Issue
    from app.models.review import Review

    table_map = {
        "issues": Issue.__table__,
        "audit_traces": AuditTrace.__table__,
        "reviews": Review.__table__,
    }
    try:
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            _prepare_review_fk_parents(conn)
            if "reviews" in needed:
                for child in ("issues", "audit_traces"):
                    if child in tables and child not in needed:
                        needed.append(child)
            for name in ("reviews", "issues", "audit_traces"):
                if name in needed:
                    _rebuild_sqlite_table_with_fk(conn, table_map[name])
            violations = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
            if violations:
                raise ReviewForeignKeyError(f"foreign key check failed: {violations[:5]}")
    except ReviewForeignKeyError:
        raise
    except Exception as exc:
        raise ReviewForeignKeyError(f"failed to apply review foreign keys: {exc}") from exc

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    from app.models import user, document, review, issue, rule, audit_basis, term, compare_task, compare_diff, compare_config, memory, translation_doc, knowledge, polished_document, convert_task, convert_rule, polish_feedback, qa_feedback, qa_history, audit_trace, competitor_task, competitor_comparison, cat_analysis_session, cat_decision_record, false_positive_memory
    Base.metadata.create_all(bind=engine)
    _ensure_legacy_sqlite_columns()
    _ensure_review_foreign_keys()
