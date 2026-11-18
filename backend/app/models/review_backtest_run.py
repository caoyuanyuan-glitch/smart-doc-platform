from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database import Base


class ReviewBacktestRun(Base):
    __tablename__ = "review_backtest_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sample_id = Column(String, index=True)
    expected_rule = Column(String, index=True)
    doc_no = Column(String)
    doc_file = Column(String)
    version_align = Column(String)  # 一致 / 基本一致 / 不一致 / 不可判定
    hit_tier = Column(String)  # TRUE_HIT / ALIGN_ONLY / TEXT_ONLY / NONE
    channel = Column(String)
    loose_hit = Column(Boolean, default=False)
    strict_hit = Column(Boolean, default=False)
    must_detect = Column(Boolean, default=False)
    miss_reason = Column(String)  # 规则族未接通 / 真实漏检 / 样本版本不可判定
    payload = Column(Text)
