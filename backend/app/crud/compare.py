from sqlalchemy.orm import Session
from app.models.compare_task import CompareTask
from app.models.compare_diff import CompareDiff
from app.schemas.compare import CompareTaskCreate
import json
from datetime import datetime

def create_compare_task(db: Session, file_a_name: str, file_b_name: str, user_id: int, group_id: int = None, file_names: str = None):
    db_task = CompareTask(
        file_a_name=file_a_name,
        file_b_name=file_b_name,
        user_id=user_id,
        group_id=group_id,
        file_names=file_names,
        status="processing"
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

def get_compare_task(db: Session, task_id: int):
    return db.query(CompareTask).filter(CompareTask.id == task_id).first()

def get_compare_tasks(db: Session, user_id: int = None, skip: int = 0, limit: int = 100):
    query = db.query(CompareTask)
    if user_id is not None:
        query = query.filter(CompareTask.user_id == user_id)
    return query.offset(skip).limit(limit).all()

def update_compare_task(db: Session, task_id: int, similarity: float, verdict: str, total_diffs: int, diff_stats: dict,
                        exact_match: int = 0, n_a: int = 0, n_b: int = 0, matched_pairs: list = None,
                        only_a: list = None, only_b: list = None, dita_full_json: str = ""):
    task = db.query(CompareTask).filter(CompareTask.id == task_id).first()
    if task:
        task.similarity = similarity
        task.verdict = verdict
        task.total_diffs = total_diffs
        task.diff_stats = json.dumps(diff_stats)
        task.status = "completed"
        task.exact_match = exact_match
        task.n_a = n_a
        task.n_b = n_b
        task.matched_pairs = json.dumps(matched_pairs or [])
        task.only_a = json.dumps(only_a or [])
        task.only_b = json.dumps(only_b or [])
        if dita_full_json and hasattr(task, "dita_full"):
            task.dita_full = dita_full_json
        db.commit()
        db.refresh(task)
    return task

def delete_compare_task(db: Session, task_id: int):
    task = db.query(CompareTask).filter(CompareTask.id == task_id).first()
    if task:
        db.query(CompareDiff).filter(CompareDiff.task_id == task_id).delete()
        db.delete(task)
        db.commit()
    return task

def create_compare_diff(db: Session, task_id: int, diff_type: str, severity: str, similarity: float,
                        text_a: str, text_b: str, position_a: dict, position_b: dict, chapter: str):
    db_diff = CompareDiff(
        task_id=task_id,
        diff_type=diff_type,
        severity=severity,
        similarity=similarity,
        text_a=text_a,
        text_b=text_b,
        position_a=json.dumps(position_a),
        position_b=json.dumps(position_b),
        chapter=chapter
    )
    db.add(db_diff)
    db.commit()
    db.refresh(db_diff)
    return db_diff

def get_compare_diffs(db: Session, task_id: int):
    return db.query(CompareDiff).filter(CompareDiff.task_id == task_id).all()


def get_compare_tasks_by_group(db: Session, group_id: int):
    return db.query(CompareTask).filter(CompareTask.group_id == group_id).order_by(CompareTask.id).all()


def get_compare_config(db: Session):
    """获取全局对比配置（单行）。无记录时创建默认行。"""
    from app.models.compare_config import CompareConfig
    config = db.query(CompareConfig).first()
    if not config:
        config = CompareConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def update_compare_config(db: Session, threshold=None, alpha=None, beta=None, tolerance=None, whitelist=None):
    """更新对比配置，仅覆盖显式传入的字段。"""
    from app.models.compare_config import CompareConfig
    import json as _json
    config = db.query(CompareConfig).first()
    if not config:
        config = CompareConfig()
        db.add(config)
    if threshold is not None:
        config.threshold = float(threshold)
    if alpha is not None:
        config.alpha = float(alpha)
    if beta is not None:
        config.beta = float(beta)
    if tolerance is not None:
        config.tolerance = float(tolerance)
    if whitelist is not None:
        config.whitelist = _json.dumps(whitelist, ensure_ascii=False) if not isinstance(whitelist, str) else whitelist
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return config
