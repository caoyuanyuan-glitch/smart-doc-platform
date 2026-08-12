"""模板分析异步 Job 管理器.

每个 UploadFile 先 POST 到此模块创建 job，后端 asyncio.create_task 后台跑
build_template_profile 并通过 progress_cb 实时更新 step/label。前端可轮询
template-status 查询进度。Job 完成后 profile 缓存在内存 dict 中，供后续
continue-text 直接取用（不需要再次上传文件）。

纯内存 + /tmp 备份；TTL 30 分钟过期清理。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

from app.utils.template_profiler import (
    build_template_profile,
    MAX_TEMPLATE_SIZE_BYTES,
)

JOBS_TTL_SECONDS = 30 * 60  # 30 分钟
JOBS_DIR = "/tmp/template_jobs"

# job_id → TemplateProfileJob
_JOBS: dict[str, "TemplateProfileJob"] = {}


@dataclass
class TemplateProfileJob:
    job_id: str
    filename: str
    size_bytes: int
    sha: str
    status: str = "analyzing"  # analyzing | done | failed
    step: int = 0
    step_label: str = "已提交，等待处理"
    profile: Optional[dict] = None
    error: Optional[str] = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    finished_at: Optional[int] = None

    def to_public_dict(self) -> dict:
        """返回给前端的轻量字典（不泄露 profile 全文）。"""
        base = {
            "job_id": self.job_id,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "step": self.step,
            "step_label": self.step_label,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }
        if self.status == "done" and self.profile:
            base["hash"] = self.profile.get("hash")
            base["parse_status"] = self.profile.get("parse_status")
            base["char_count"] = self.profile.get("char_count")
            base["section_count"] = self.profile.get("section_count")
            base["fallback_reason"] = self.profile.get("fallback_reason")
        if self.status == "failed":
            base["error"] = self.error
        return base


def _sha(filename: str, raw: bytes) -> str:
    return hashlib.sha256((filename or "").encode() + (raw or b"")).hexdigest()


def get_job(job_id: str) -> Optional[TemplateProfileJob]:
    _expire_old_jobs()
    job = _JOBS.get(job_id)
    if job and job.status != "analyzing":
        return job
    # 尝试从磁盘恢复（进程重启场景）
    if job is None:
        disk_path = os.path.join(JOBS_DIR, f"{job_id}.json")
        if os.path.exists(disk_path):
            try:
                with open(disk_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status") != "analyzing":
                    job = TemplateProfileJob(**data)
                    _JOBS[job_id] = job
                    return job
            except Exception:
                pass
    return job


def _persist_job(job: TemplateProfileJob) -> None:
    try:
        os.makedirs(JOBS_DIR, exist_ok=True)
        with open(os.path.join(JOBS_DIR, f"{job.job_id}.json"), "w", encoding="utf-8") as f:
            json.dump(asdict(job), f, ensure_ascii=False)
    except Exception:
        pass


def _expire_old_jobs() -> None:
    now = int(time.time())
    expired = [
        jid for jid, j in _JOBS.items()
        if j.status in ("done", "failed") and (now - (j.finished_at or j.created_at)) > JOBS_TTL_SECONDS
    ]
    for jid in expired:
        _JOBS.pop(jid, None)
        try:
            os.remove(os.path.join(JOBS_DIR, f"{jid}.json"))
        except Exception:
            pass


def create_job(filename: str, raw: bytes) -> TemplateProfileJob:
    """创建异步 job 并返回，后续由调用方（FastAPI endpoint）launch。"""
    size = len(raw or b"")
    if size > MAX_TEMPLATE_SIZE_BYTES:
        raise ValueError(
            f"模板文件过大：{size / 1024 / 1024:.1f} MB，"
            f"上限 {MAX_TEMPLATE_SIZE_BYTES / 1024 / 1024:.0f} MB"
        )

    sha = _sha(filename, raw)

    # 已存在相同文件且 job 已完成 → 直接返回完成状态的 job
    for j in _JOBS.values():
        if j.sha == sha and j.status == "done" and j.profile:
            return j

    job_id = uuid.uuid4().hex[:16]
    job = TemplateProfileJob(
        job_id=job_id,
        filename=filename or "未命名模板",
        size_bytes=size,
        sha=sha,
        step=0,
        step_label="已提交，等待处理",
    )
    _JOBS[job_id] = job
    _persist_job(job)
    return job


def launch_job(job_id: str, raw: bytes, loop=None) -> None:
    """用 asyncio.create_task 在后台启动 profile 构建。"""
    job = _JOBS.get(job_id)
    if not job or job.status != "analyzing":
        return

    if loop is None:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return

    async def _background():
        try:
            profile = await loop.run_in_executor(
                None,
                _run_sync_build,
                job, raw,
            )
            job.profile = profile
            job.status = "done"
            job.step = 5
            job.step_label = "完成"
        except ValueError as e:
            job.status = "failed"
            job.error = str(e)
            job.step_label = f"失败：{e}"
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.step_label = f"构建异常：{e}"
        finally:
            job.finished_at = int(time.time())
            _persist_job(job)

    asyncio.ensure_future(_background(), loop=loop)


def _run_sync_build(job: TemplateProfileJob, raw: bytes) -> Optional[dict]:
    def cb(step: int, label: str):
        job.step = step
        job.step_label = label
        _persist_job(job)

    return build_template_profile(job.filename, raw, progress_cb=cb)
