from __future__ import annotations

from app.crud.review import seed_preset_false_positive_memory
from app.database import SessionLocal, create_tables
from app.models.false_positive_memory import FalsePositiveMemory


def main() -> None:
    create_tables()
    db = SessionLocal()
    try:
        inserted = seed_preset_false_positive_memory(db)
        total = db.query(FalsePositiveMemory).count()
        print({"inserted": inserted, "total": total})
    finally:
        db.close()


if __name__ == "__main__":
    main()
