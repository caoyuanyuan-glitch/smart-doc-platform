from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime


class Competitor(Base):
    """竞品表"""
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="竞品名称")
    brand = Column(String(100), comment="品牌")
    website = Column(String(255), comment="官网地址")
    description = Column(Text, comment="竞品简介")
    tags = Column(String(255), comment="标签（逗号分隔）")
    user_id = Column(Integer, comment="创建者")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关联文档
    documents = relationship("CompetitorDocument", back_populates="competitor", cascade="all, delete-orphan")
    # 关联对比任务
    compare_tasks = relationship("CompetitorCompareTask", back_populates="competitor", cascade="all, delete-orphan")
    # 关联公众号
    wechat_accounts = relationship("WechatAccount", back_populates="competitor", cascade="all, delete-orphan")


class WechatAccount(Base):
    """公众号配置表"""
    __tablename__ = "wechat_accounts"

    id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("competitors.id"), nullable=False, comment="所属竞品")
    account_name = Column(String(100), nullable=False, comment="公众号名称")
    account_id = Column(String(100), comment="微信号/原始ID")
    description = Column(Text, comment="公众号简介")
    is_active = Column(Integer, default=1, comment="是否启用: 1启用 / 0禁用")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关联竞品
    competitor = relationship("Competitor", back_populates="wechat_accounts")
    # 关联文章
    articles = relationship("WechatArticle", back_populates="wechat_account", cascade="all, delete-orphan")


class WechatArticle(Base):
    """公众号文章表"""
    __tablename__ = "wechat_articles"

    id = Column(Integer, primary_key=True, index=True)
    wechat_account_id = Column(Integer, ForeignKey("wechat_accounts.id"), nullable=False, comment="所属公众号")
    competitor_id = Column(Integer, ForeignKey("competitors.id"), nullable=False, comment="所属竞品（方便查询）")
    title = Column(String(255), nullable=False, comment="文章标题")
    url = Column(String(500), nullable=False, comment="文章链接")
    author = Column(String(100), comment="作者")
    publish_date = Column(DateTime, comment="发布时间")
    content = Column(Text, comment="文章内容")
    summary = Column(Text, comment="AI摘要")
    keywords = Column(String(500), comment="关键词（逗号分隔）")
    tags = Column(String(500), comment="用户标签（逗号分隔）")
    category = Column(String(50), comment="文章分类: 产品介绍 / 技术分享 / 行业动态 / 活动推广 / 其他")
    notes = Column(Text, comment="备注")
    collected_at = Column(DateTime, default=datetime.utcnow, comment="采集时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关联公众号
    wechat_account = relationship("WechatAccount", back_populates="articles")


class CompetitorDocument(Base):
    """竞品文档表"""
    __tablename__ = "competitor_documents"

    id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("competitors.id"), nullable=False, comment="所属竞品")
    doc_type = Column(String(20), nullable=False, comment="文档类型: competitor(竞品) / ours(我方)")
    file_name = Column(String(255), nullable=False, comment="文件名")
    file_path = Column(String(255), nullable=False, comment="文件路径")
    file_type = Column(String(20), comment="文件格式: pdf / docx / dita")
    file_size = Column(Integer, default=0, comment="文件大小（字节）")
    version = Column(String(50), comment="版本号")
    notes = Column(Text, comment="备注")
    upload_date = Column(DateTime, default=datetime.utcnow, comment="上传时间")

    # 关联竞品
    competitor = relationship("Competitor", back_populates="documents")


class CompetitorCompareTask(Base):
    """竞品对比任务表"""
    __tablename__ = "competitor_compare_tasks"

    id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("competitors.id"), nullable=False, comment="所属竞品")
    competitor_doc_id = Column(Integer, ForeignKey("competitor_documents.id"), nullable=False, comment="竞品文档ID")
    our_doc_id = Column(Integer, ForeignKey("competitor_documents.id"), nullable=False, comment="我方文档ID")
    status = Column(String(20), default="pending", comment="状态: pending / processing / completed / failed")
    similarity = Column(Float, comment="总体相似度")
    result_data = Column(Text, comment="对比结果JSON")
    suggestions = Column(Text, comment="AI改进建议JSON")
    error_message = Column(Text, comment="错误信息")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    completed_at = Column(DateTime, comment="完成时间")

    # 关联竞品
    competitor = relationship("Competitor", back_populates="compare_tasks")
    # 关联竞品文档
    competitor_doc = relationship("CompetitorDocument", foreign_keys=[competitor_doc_id])
    our_doc = relationship("CompetitorDocument", foreign_keys=[our_doc_id])