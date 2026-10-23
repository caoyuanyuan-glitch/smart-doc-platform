from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime

from app.database import Base


class CompetitorComparison(Base):
    """竞品文档对比任务。

    聚合 2-5 个已完成的竞品分析任务（CompetitorTask）做横向对比：
    维度分数矩阵 / 每维度最优 / 综合排名（含我方基线标记）/ 差距洞察。
    对比结果结构存 result_json（前端雷达图与矩阵直接消费），
    报告全文存 report_md，便于列表页预览与导出。
    """
    __tablename__ = "competitor_comparisons"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    task_ids = Column(Text)             # JSON 数组：参与对比的任务 ID（按选择顺序）
    baseline_task_id = Column(Integer)  # 我方基线任务 ID（可空）
    result_json = Column(Text)          # JSON：对比结构结果
    report_md = Column(Text)            # Markdown 对比报告全文
    user_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
