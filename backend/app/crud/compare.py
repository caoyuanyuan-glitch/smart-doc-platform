from sqlalchemy.orm import Session
from app.models.compare_task import CompareTask
from app.models.compare_diff import CompareDiff
from app.models.compare_config import CompareConfig
from app.schemas.compare import CompareTaskCreate
import json

def create_compare_task(db: Session, file_a_name: str, file_b_name: str, user_id: int):
    db_task = CompareTask(
        file_a_name=file_a_name,
        file_b_name=file_b_name,
        user_id=user_id,
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

def update_compare_task(db: Session, task_id: int, similarity: float, verdict: str, total_diffs: int, diff_stats: dict):
    task = db.query(CompareTask).filter(CompareTask.id == task_id).first()
    if task:
        task.similarity = similarity
        task.verdict = verdict
        task.total_diffs = total_diffs
        task.diff_stats = json.dumps(diff_stats)
        task.status = "completed"
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

def get_compare_config(db: Session):
    config = db.query(CompareConfig).first()
    if not config:
        config = CompareConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

def update_compare_config(db: Session, threshold: float = None, alpha: float = None,
                          beta: float = None, tolerance: float = None, whitelist: list = None):
    config = get_compare_config(db)
    if threshold is not None:
        config.threshold = threshold
    if alpha is not None:
        config.alpha = alpha
    if beta is not None:
        config.beta = beta
    if tolerance is not None:
        config.tolerance = tolerance
    if whitelist is not None:
        config.whitelist = json.dumps(whitelist)
    db.commit()
    db.refresh(config)
    return config
