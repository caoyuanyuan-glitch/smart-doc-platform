from sqlalchemy import create_engine, inspect, text
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

    try:
        diagnose_tables = set(inspector.get_table_names())
    except Exception:
        diagnose_tables = set()
    if "cat_diagnose_record_lab" in diagnose_tables:
        try:
            diagnose_columns = {col["name"] for col in inspector.get_columns("cat_diagnose_record_lab")}
        except Exception:
            diagnose_columns = set()
        with engine.begin() as conn:
            if "source_name" not in diagnose_columns:
                conn.execute(text("ALTER TABLE cat_diagnose_record_lab ADD COLUMN source_name VARCHAR(255)"))
            conn.execute(text(
                "UPDATE cat_diagnose_record_lab SET ruleable = 1 "
                "WHERE COALESCE(ruleable, 0) = 0 "
                "AND revised IS NOT NULL AND TRIM(revised) != ''"
            ))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    from app.models import user, document, review, issue, rule, audit_basis, term, compare_task, compare_diff, compare_config, memory, translation_doc, knowledge, polished_document, polished_document_lab, convert_task, convert_rule, polish_feedback, polish_feedback_lab, qa_feedback, qa_history, audit_trace, competitor_task, cat_analysis_session, cat_analysis_session_lab, cat_decision_record, cat_decision_record_lab, false_positive_memory
    from app.models import cat_diagnose_record_lab
    Base.metadata.create_all(bind=engine)
    _ensure_legacy_sqlite_columns()
