from sqlalchemy.orm import Session

from app.models.audit_trace import AuditTrace


def get_traces_by_review_id(db: Session, review_id: int):
    return (
        db.query(AuditTrace)
        .filter(AuditTrace.review_id == review_id)
        .order_by(AuditTrace.chunk_index.asc(), AuditTrace.id.asc())
        .all()
    )


def sync_traces_from_usage_events(
    db: Session,
    review_id: int,
    usage_events: list[dict],
    chunk_sizes: list[int] | None = None,
    issue_counts: list[int] | None = None,
):
    existing_keys = {
        (
            trace.review_id,
            trace.chunk_index,
            trace.provider,
            trace.model,
            trace.total_tokens,
            trace.request_label,
        )
        for trace in get_traces_by_review_id(db, review_id)
    }

    created = []
    chunk_sizes = list(chunk_sizes or [])
    issue_counts = list(issue_counts or [])

    for index, event in enumerate(usage_events or [], start=1):
        trace = AuditTrace(
            review_id=review_id,
            request_label=str(event.get("request_label") or "generic"),
            chunk_index=index,
            chunk_size=int(chunk_sizes[index - 1] or 0) if index - 1 < len(chunk_sizes) else 0,
            provider=str(event.get("provider") or "unknown"),
            model=str(event.get("model") or ""),
            prompt_tokens=int(event.get("prompt_tokens") or 0),
            completion_tokens=int(event.get("completion_tokens") or 0),
            total_tokens=int(event.get("total_tokens") or 0),
            latency_ms=int(event.get("elapsed_ms")) if event.get("elapsed_ms") is not None else 0,
            status="ok",
            error_message=None,
            parsed_issue_count=int(issue_counts[index - 1] or 0) if index - 1 < len(issue_counts) else 0,
        )
        key = (
            trace.review_id,
            trace.chunk_index,
            trace.provider,
            trace.model,
            trace.total_tokens,
            trace.request_label,
        )
        if key in existing_keys:
            continue

        db.add(trace)
        created.append(trace)
        existing_keys.add(key)

    if created:
        db.commit()
    return created
