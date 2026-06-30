from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.database import Base


class PolishLearningRule(Base):
    __tablename__ = "polish_learning_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_name = Column(String(128), nullable=True, comment="规则名称（如'术语替换''祈使句规范'）")
    rule_type = Column(String(64), index=True, nullable=False, comment="规则分类：system_rule/replacement_rule/forbidden_rule/sentence_applicability_rule")
    engine_key = Column(String(64), nullable=True, unique=True, comment="引擎规则键，仅系统规则有值（如 termReplace/imperativePlease）")
    rule_key = Column(String(128), unique=True, index=True, nullable=False)
    match_pattern = Column(Text, nullable=False)
    replacement_text = Column(Text, nullable=True)
    description = Column(Text, nullable=True, comment="规则说明/用途描述")
    priority_level = Column(Integer, default=0)
    trigger_count = Column(Integer, default=0)
    last_triggered_at = Column(DateTime, nullable=True)
    source_feedback_id = Column(Integer, ForeignKey("polish_feedback_records.id"), nullable=True)
    knowledge_file_id = Column(Integer, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
