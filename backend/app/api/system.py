from fastapi import APIRouter, Depends
from app.utils.ai_client import ai_client
from app.api.auth import get_current_active_user, require_admin
from app.schemas.user import UserOut

router = APIRouter()


@router.get("/ai-status")
async def ai_status(_: UserOut = Depends(get_current_active_user)):
    return ai_client.health_check()


@router.post("/ai-warmup")
async def ai_warmup(_: UserOut = Depends(require_admin)):
    return ai_client.warmup()


@router.get("/ai-usage")
async def ai_usage(limit: int = 50, _: UserOut = Depends(require_admin)):
    safe_limit = max(10, min(int(limit or 50), 200))
    return ai_client.usage_dashboard(limit=safe_limit)
