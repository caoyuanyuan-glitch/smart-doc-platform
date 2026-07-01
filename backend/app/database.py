from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

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

    try:
        review_columns = {col['name'] for col in inspector.get_columns('reviews')}
    except Exception:
        review_columns = set()

    if review_columns and 'completed_at' not in review_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE reviews ADD COLUMN completed_at DATETIME"))

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
        translation_doc_columns = {col['name'] for col in inspector.get_columns('translation_docs')}
    except Exception:
        translation_doc_columns = set()

    if translation_doc_columns and 'source_char_count' not in translation_doc_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN source_char_count INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN ai_char_count INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE translation_docs ADD COLUMN memory_char_count INTEGER DEFAULT 0"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    from app.models import user, document, review, issue, rule, audit_basis, term, compare_task, compare_diff, compare_config, memory, translation_doc, knowledge, polished_document, convert_task, convert_rule, polish_feedback, qa_feedback, qa_history
    Base.metadata.create_all(bind=engine)
    _ensure_legacy_sqlite_columns()
