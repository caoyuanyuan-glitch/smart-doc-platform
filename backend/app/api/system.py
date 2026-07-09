from fastapi import APIRouter
from app.utils.ai_client import ai_client

router = APIRouter()


@router.get("/ai-status")
async def ai_status():
    return ai_client.health_check()


@router.post("/ai-warmup")
async def ai_warmup():
    return ai_client.warmup()
