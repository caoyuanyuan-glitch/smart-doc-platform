from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger
from app.database import Base
from datetime import datetime


class CompetitorTask(Base):
    """竞品文档分析任务。

    每次上传一份竞品文档（PDF/Word/Markdown）生成一个分析任务，
    分析结果（编辑工具识别 / 可读性）以 JSON 文本列存储，
    Markdown 报告整篇存入 report_md，便于列表页直接预览与导出。
    """
    __tablename__ = "competitor_tasks"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String)
    file_size = Column(BigInteger, default=0)
    status = Column(String, default="pending")  # pending / processing / completed / failed
    tool_analysis = Column(Text)   # JSON: 编辑工具识别结果
    readability = Column(Text)     # JSON: 可读性分析结果
    report_md = Column(Text)       # Markdown 报告全文
    error = Column(Text)           # 失败原因
    user_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
