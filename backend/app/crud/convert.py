from sqlalchemy.orm import Session
from app.models.convert_task import ConvertTask
from app.schemas.convert import ConvertTaskCreate
import json


def create_convert_task(db: Session, task: ConvertTaskCreate) -> ConvertTask:
    import time
    task_id = f"conv_{int(time.time() * 1000)}"
    db_task = ConvertTask(
        task_id=task_id,
        source_filename=task.source_filename,
        source_format=task.source_format,
        target_format=task.target_format,
        template_filename=task.template_filename,
        requirements=task.requirements,
        status="processing",
        progress=0,
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def get_convert_task(db: Session, task_id: str) -> ConvertTask:
    return db.query(ConvertTask).filter(ConvertTask.task_id == task_id).first()


def get_convert_tasks(db: Session, skip: int = 0, limit: int = 100):
    return db.query(ConvertTask).order_by(ConvertTask.created_at.desc()).offset(skip).limit(limit).all()


def update_convert_task_status(db: Session, task_id: str, status: str, progress: int = None,
                                current_step: str = None):
    task = get_convert_task(db, task_id)
    if task:
        task.status = status
        if progress is not None:
            task.progress = progress
        if current_step is not None:
            task.current_step = current_step
        db.commit()
        db.refresh(task)
    return task


def update_convert_task_result(db: Session, task_id: str, output_zip_path: str, output_size: int,
                                topic_count: int, image_count: int, verification_report: dict,
                                conversion_detail: list):
    task = get_convert_task(db, task_id)
    if task:
        task.status = "completed"
        task.progress = 100
        task.current_step = "打包"
        task.output_zip_path = output_zip_path
        task.output_size = output_size
        task.topic_count = topic_count
        task.image_count = image_count
        task.verification_report = json.dumps(verification_report, ensure_ascii=False)
        task.conversion_detail = json.dumps(conversion_detail, ensure_ascii=False)
        db.commit()
        db.refresh(task)
    return task


def update_convert_task_failed(db: Session, task_id: str, error_message: str):
    task = get_convert_task(db, task_id)
    if task:
        task.status = "failed"
        task.error_message = error_message
        db.commit()
        db.refresh(task)
    return task


def update_convert_task_progress(db: Session, task_id: str, progress: int, current_step: str):
    task = get_convert_task(db, task_id)
    if task:
        task.progress = progress
        task.current_step = current_step
        db.commit()
    return task


def delete_convert_task(db: Session, task_id: str):
    task = get_convert_task(db, task_id)
    if task:
        import os
        if task.output_zip_path:
            file_path = f".{task.output_zip_path}"
            if os.path.exists(file_path):
                os.remove(file_path)
        db.delete(task)
        db.commit()
    return task
