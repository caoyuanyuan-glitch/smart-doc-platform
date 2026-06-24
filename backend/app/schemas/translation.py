from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TranslationRequest(BaseModel):
    content: str
    engine: str = "hybrid"
    model: str = "kimi"
    source_lang: str = "zh"
    target_lang: str = "en"
    memory_bank: Optional[str] = None
    memory_file_id: Optional[int] = None


class TranslationResponse(BaseModel):
    original: str
    translated: str
    engine_used: str
    from_memory: bool = False
    from_ai: bool = False


class MemoryEntry(BaseModel):
    source_text: str
    translated_text: str
    source_lang: str = "zh"
    target_lang: str = "en"
    tags: str = ""


class MemoryEntryOut(BaseModel):
    id: int
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    tags: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TranslationDocOut(BaseModel):
    id: int
    filename: str
    file_type: str
    source_lang: str
    target_lang: str
    engine: str
    model: str
    original_preview: str
    translated_preview: str
    original_content: str
    translated_content: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
