from sqlalchemy.orm import Session
from app.models.competitor_task import CompetitorTask
import json


def create_competitor_task(db: Session, file_name: str, file_size: int, user_id: int):
    db_task = CompetitorTask(
        file_name=file_name,
        file_size=file_size,
        user_id=user_id,
        status="processing"
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def get_competitor_task(db: Session, task_id: int):
    return db.query(CompetitorTask).filter(CompetitorTask.id == task_id).first()


def get_competitor_tasks(db: Session, user_id: int = None, skip: int = 0, limit: int = 100):
    query = db.query(CompetitorTask)
    if user_id is not None:
        query = query.filter(CompetitorTask.user_id == user_id)
    return query.order_by(CompetitorTask.id.desc()).offset(skip).limit(limit).all()


def update_competitor_task(db: Session, task_id: int, *, status: str = None,
                           tool_analysis: dict = None, readability: dict = None,
                           report_md: str = None, error: str = None, completed_at=None):
    task = db.query(CompetitorTask).filter(CompetitorTask.id == task_id).first()
    if not task:
        return None
    if status is not None:
        task.status = status
    if tool_analysis is not None:
        task.tool_analysis = json.dumps(tool_analysis, ensure_ascii=False)
    if readability is not None:
        task.readability = json.dumps(readability, ensure_ascii=False)
    if report_md is not None:
        task.report_md = report_md
    if error is not None:
        task.error = error
    if completed_at is not None:
        task.completed_at = completed_at
    db.commit()
    db.refresh(task)
    return task


def delete_competitor_task(db: Session, task_id: int):
    task = db.query(CompetitorTask).filter(CompetitorTask.id == task_id).first()
    if task:
        db.delete(task)
        db.commit()
    return task


# ------------------------------------------------------------ 多文档对比

def create_competitor_comparison(db: Session, *, title: str, task_ids: list,
                                 baseline_task_id=None, result: dict,
                                 report_md: str, user_id: int):
    from app.models.competitor_comparison import CompetitorComparison
    db_item = CompetitorComparison(
        title=title,
        task_ids=json.dumps(task_ids, ensure_ascii=False),
        baseline_task_id=baseline_task_id,
        result_json=json.dumps(result, ensure_ascii=False),
        report_md=report_md,
        user_id=user_id,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def get_competitor_comparison(db: Session, comparison_id: int):
    from app.models.competitor_comparison import CompetitorComparison
    return db.query(CompetitorComparison).filter(CompetitorComparison.id == comparison_id).first()


def get_competitor_comparisons(db: Session, user_id: int = None, skip: int = 0, limit: int = 100):
    from app.models.competitor_comparison import CompetitorComparison
    query = db.query(CompetitorComparison)
    if user_id is not None:
        query = query.filter(CompetitorComparison.user_id == user_id)
    return query.order_by(CompetitorComparison.id.desc()).offset(skip).limit(limit).all()


def delete_competitor_comparison(db: Session, comparison_id: int):
    item = get_competitor_comparison(db, comparison_id)
    if item:
        db.delete(item)
        db.commit()
    return item
