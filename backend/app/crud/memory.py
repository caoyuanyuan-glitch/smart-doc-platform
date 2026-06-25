from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.memory import MemoryBank


def create_memory_entry(db: Session, source_text: str, translated_text: str,
                        source_lang: str = "zh", target_lang: str = "en", tags: str = ""):
    entry = MemoryBank(
        source_text=source_text,
        translated_text=translated_text,
        source_lang=source_lang,
        target_lang=target_lang,
        tags=tags
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_memory_entries(db: Session, skip: int = 0, limit: int = 100, keyword: str = None):
    query = db.query(MemoryBank)
    if keyword:
        query = query.filter(
            or_(
                MemoryBank.source_text.contains(keyword),
                MemoryBank.translated_text.contains(keyword),
                MemoryBank.tags.contains(keyword)
            )
        )
    return query.order_by(MemoryBank.created_at.desc()).offset(skip).limit(limit).all()


def search_memory(db: Session, source_text: str, source_lang: str = "zh", target_lang: str = "en",
                  threshold: float = 0.7, bank: str = None):
    query = db.query(MemoryBank).filter(
        MemoryBank.source_lang == source_lang,
        MemoryBank.target_lang == target_lang
    )
    if bank:
        query = query.filter(MemoryBank.tags == bank)
    entries = query.all()

    best_match = None
    for entry in entries:
        if entry.source_text.strip() == source_text.strip():
            return entry.translated_text

        if len(source_text) > 20:
            shorter = min(entry.source_text, source_text, key=len)
            longer = max(entry.source_text, source_text, key=len)
            overlap = sum(1 for c in shorter if c in longer)
            similarity = overlap / len(longer) if longer else 0
            if similarity > threshold:
                best_match = entry.translated_text

    return best_match


def get_memory_entry(db: Session, entry_id: int):
    return db.query(MemoryBank).filter(MemoryBank.id == entry_id).first()


def delete_memory_entry(db: Session, entry_id: int):
    entry = db.query(MemoryBank).filter(MemoryBank.id == entry_id).first()
    if entry:
        db.delete(entry)
        db.commit()
    return entry


def get_memory_banks(db: Session):
    """Return distinct tag values (memory banks) from the memory table."""
    from sqlalchemy import distinct
    rows = db.query(distinct(MemoryBank.tags)).filter(MemoryBank.tags != "").all()
    banks = [row[0] for row in rows if row[0]]
    return sorted(banks)
