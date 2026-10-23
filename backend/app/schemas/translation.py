from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TranslationRequest(BaseModel):
    content: str
    engine: str = "hybrid"
    model: str = "kimi"
    source_lang: str = "auto"
    target_lang: str = "en"
    memory_bank: Optional[str] = None
    memory_file_id: Optional[int] = None
    memory_file_ids: Optional[list[int]] = None


class MemoryMatchDiffSpan(BaseModel):
    text: str
    tag: str


class MemoryMatchDetail(BaseModel):
    source_text: str
    candidate_text: str
    translated_text: str = ""
    match_rate: float
    reason: str = ""
    source_spans: List[MemoryMatchDiffSpan] = []
    candidate_spans: List[MemoryMatchDiffSpan] = []
    leftover_fragments: List[str] = []


class TranslationResponse(BaseModel):
    original: str
    translated: str
    engine_used: str
    from_memory: bool = False
    from_ai: bool = False
    source_word_count: int = 0
    ai_word_count: int = 0
    memory_word_count: int = 0
    memory_matches: List[MemoryMatchDetail] = []


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


class MemoryFileEntryRequest(BaseModel):
    memory_file_id: int
    source_text: str
    translated_text: str
    source_lang: str = "zh"
    target_lang: str = "en"


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
    batch_id: str = ""
    translated_filename: str = ""
    file_size: int = 0
    duration_ms: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
