"""人工补录漏检问题的回流快照表。

每次人工在问题详情页"补录"一条平台漏检问题，除了创建 Issue（source=manual）
之外，同步在此表落一份结构化快照（含位置），作为后续三条进化管线的原料：
  1. 同类聚类 -> 自动生成规则草案（rule_candidate_status 跟踪状态）；
  2. 评测回测：新规则 / 规则改动后，用本表数据验证是否真的学会了；
  3. AI few-shot 知识库：原文 -> 建议对直接进 AI 深度审核示例。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.database import Base


class SupplementFeedback(Base):
    __tablename__ = "review_supplement_feedback"
    __table_args__ = (
        UniqueConstraint("review_id", "issue_id", name="uq_supplement_review_issue"),
    )

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_id = Column(Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    category = Column(String, default="人工补充")
    severity = Column(String, default="general")
    chapter = Column(String)
    original_text = Column(Text)
    suggestion = Column(Text)
    context = Column(Text)
    position = Column(Text)  # JSON: {"page_number":..,"chapter":..,"char_start":..,"char_end":..,"position_object":{..}}
    rule_candidate_status = Column(String, default="open")  # open / rule_draft / converted / dismissed
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
