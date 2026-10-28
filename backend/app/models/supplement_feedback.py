"""人工审核意见回流快照 + 批量导入样本池 共用表。

两个来源汇入同一张表：
1. 人工在问题详情页"补录"一条平台漏检问题（review_id/issue_id 非空，
   与 Issue 行一一对应）——PR #159 已有行为；
2. 批量导入已整理好的人工审核意见（md/json/csv，review_id/issue_id 可空，
   靠 doc_name/page/comment 定位）——本次新增，让"整理出来的意见"直接入库。

后续三条进化管线共用本表：
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
    # 补录来源必填；批量导入来源（review_id/issue_id 为 NULL，靠 doc_name/page/comment 定位）
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=True, index=True)
    issue_id = Column(Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    # 批量导入来源的文档定位字段
    doc_name = Column(String(512))
    page = Column(String(32))
    annotation_type = Column(String(64))
    author = Column(String(128))
    comment = Column(Text)
    category = Column(String(128), default="人工补充")
    severity = Column(String, default="general")
    chapter = Column(String)
    original_text = Column(Text)
    suggestion = Column(Text)
    context = Column(Text)
    position = Column(Text)  # JSON: {"page_number":..,"chapter":..,"char_start":..,"char_end":..,"position_object":{..}}
    layer = Column(String(32), default="ai_assisted")  # ai / deterministic / ai_assisted
    expected_rule = Column(String(128))
    source = Column(String(32), default="manual")  # manual(补录) / batch_import(批量导入)
    batch_name = Column(String(128), index=True)
    rule_candidate_status = Column(String, default="open")  # open / rule_draft / converted / dismissed
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
