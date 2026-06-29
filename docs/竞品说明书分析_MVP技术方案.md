# 竞品说明书分析 MVP 技术方案

## 一、技术架构概览

### 1.1 复用现有能力

| 现有模块 | 复用内容 | 复用方式 |
|---------|---------|---------|
| 文档对比引擎 | 文本对比、章节检测、相似度计算 | 直接调用 `doc_parser.py` 和 `compare_utils.py` |
| AI客户端 | AI对话、摘要生成 | 直接调用 `ai_client.py` |
| 报告生成 | HTML报告模板、差异高亮 | 复用 `doc_report.py` 模板样式 |
| PDF预览组件 | 双栏预览、同步滚动 | 在对比页面复用 `PdfPreview.vue` |

### 1.2 新增模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 竞品数据模型 | `models/competitor.py` | 竞品、文档数据表 |
| 竞品API | `api/competitor.py` | 竞品管理、对比、建议接口 |
| 竞品CRUD | `crud/competitor.py` | 数据库操作 |
| 竞品Schema | `schemas/competitor.py` | 请求/响应数据结构 |
| 竞品前端页面 | `views/Competitor.vue` | 竞品管理页面 |
| 对比详情页 | `views/CompetitorCompare.vue` | 对比结果展示 |

---

## 二、数据库模型设计

### 2.1 竞品表 (competitors)

```python
class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # 竞品名称
    brand = Column(String(100))  # 品牌
    website = Column(String(255))  # 官网地址
    description = Column(Text)  # 竞品简介
    tags = Column(String(255))  # 标签（逗号分隔）
    user_id = Column(Integer)  # 创建者
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 2.2 竞品文档表 (competitor_documents)

```python
class CompetitorDocument(Base):
    __tablename__ = "competitor_documents"

    id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("competitors.id"))  # 所属竞品
    doc_type = Column(String(20))  # 文档类型: competitor(竞品) / ours(我方)
    file_name = Column(String(255), nullable=False)  # 文件名
    file_path = Column(String(255), nullable=False)  # 文件路径
    file_type = Column(String(20))  # 文件格式: pdf / docx / dita
    version = Column(String(50))  # 版本号
    upload_date = Column(DateTime, default=datetime.utcnow)  # 上传时间
    notes = Column(Text)  # 备注
```

### 2.3 对比任务表 (competitor_compare_tasks)

```python
class CompetitorCompareTask(Base):
    __tablename__ = "competitor_compare_tasks"

    id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("competitors.id"))  # 所属竞品
    competitor_doc_id = Column(Integer, ForeignKey("competitor_documents.id"))  # 竞品文档
    our_doc_id = Column(Integer, ForeignKey("competitor_documents.id"))  # 我方文档
    status = Column(String(20), default="pending")  # pending / processing / completed / failed
    similarity = Column(Float)  # 总体相似度
    result_data = Column(Text)  # 对比结果JSON
    suggestions = Column(Text)  # AI改进建议JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
```

---

## 三、后端API设计

### 3.1 竞品管理接口

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 竞品列表 | GET | `/api/competitor` | 获取竞品列表，支持分页、搜索、筛选 |
| 竞品详情 | GET | `/api/competitor/{id}` | 获取单个竞品详情 |
| 新增竞品 | POST | `/api/competitor` | 创建新竞品 |
| 编辑竞品 | PUT | `/api/competitor/{id}` | 更新竞品信息 |
| 删除竞品 | DELETE | `/api/competitor/{id}` | 删除竞品及其文档 |

### 3.2 文档管理接口

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 文档列表 | GET | `/api/competitor/{id}/documents` | 获取竞品的文档列表 |
| 上传文档 | POST | `/api/competitor/{id}/documents` | 上传竞品/我方文档 |
| 删除文档 | DELETE | `/api/competitor/{id}/documents/{doc_id}` | 删除文档 |

### 3.3 对比分析接口

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 创建对比任务 | POST | `/api/competitor/{id}/compare` | 选择竞品和我方文档，发起对比 |
| 对比任务列表 | GET | `/api/competitor/{id}/compare/tasks` | 获取对比任务历史 |
| 对比任务详情 | GET | `/api/competitor/{id}/compare/tasks/{task_id}` | 获取对比结果 |
| 对比报告导出 | GET | `/api/competitor/{id}/compare/tasks/{task_id}/export` | 导出HTML/PDF报告 |

### 3.4 AI建议接口

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 生成改进建议 | POST | `/api/competitor/{id}/compare/tasks/{task_id}/suggest` | 基于对比结果生成AI建议 |
| 获取建议详情 | GET | `/api/competitor/{id}/compare/tasks/{task_id}/suggest` | 获取已生成的建议 |

---

## 四、核心流程设计

### 4.1 竞品 vs 我方对比流程

```
用户上传竞品文档 + 我方文档
        ↓
创建对比任务 (status=pending)
        ↓
调用 doc_parser.py 解析两份文档
        ↓
调用 compare_utils.py 进行对比分析
        ↓
生成对比结果（章节差异、内容差异、相似度）
        ↓
保存结果到 result_data 字段 (status=completed)
        ↓
前端展示对比报告
        ↓
用户点击"生成改进建议"
        ↓
调用 ai_client.py 分析对比结果
        ↓
生成结构化改进建议，保存到 suggestions 字段
```

### 4.2 AI改进建议生成

Prompt模板：
```
你是一位专业的技术文档专家。请分析以下竞品说明书与我方说明书的对比结果，给出具体的改进建议。

对比结果：
- 总体相似度：{similarity}%
- 章节结构差异：{structure_diff}
- 内容差异点：{content_diff}

请从以下维度给出建议：
1. 内容补充建议：竞品有但我方缺失的重要内容
2. 结构优化建议：竞品信息架构的优势点
3. 参数对标建议：技术参数的差异说明
4. 文案优化建议：竞品的优秀表述方式

每条建议请包含：
- 建议内容
- 原因说明
- 参考竞品原文
- 优先级（高/中/低）
```

---

## 五、前端页面设计

### 5.1 竞品管理页面 (Competitor.vue)

**页面结构：**
```
┌─────────────────────────────────────────────────────┐
│ 竞品说明书分析                                        │
├─────────────────────────────────────────────────────┤
│ [新增竞品]  [搜索框]                                  │
├─────────────────────────────────────────────────────┤
│ 竞品列表表格                                          │
│ ┌─────┬────────┬──────┬──────┬────────┬─────────┐ │
│ │ ID  │ 名称   │ 品牌 │ 官网 │ 文档数  │ 操作    │ │
│ ├─────┼────────┼──────┼──────┼────────┼─────────┤ │
│ │ 1   │ 竞品A  │ XXX  │ url  │ 2      │ 详情 删除│ │
│ │ 2   │ 竞品B  │ YYY  │ url  │ 3      │ 详情 删除│ │
│ └─────┴────────┴──────┴──────┴────────┴─────────┘ │
└─────────────────────────────────────────────────────┘
```

### 5.2 竞品详情/对比页面 (CompetitorCompare.vue)

**页面结构：**
```
┌─────────────────────────────────────────────────────┐
│ 竞品：XXX产品                                         │
├─────────────────────────────────────────────────────┤
│ [上传文档]                                            │
│ ┌─────────────────────────────────────────────────┐ │
│ │ 竞品文档 (2)    │ 我方文档 (1)                   │ │
│ │ - 说明书v2.pdf  │ - 我方说明书.pdf               │ │
│ │ - 说明书v1.pdf  │                                │ │
│ └─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│ 对比分析                                              │
│ 选择竞品文档: [说明书v2.pdf ▼]                       │
│ 选择我方文档: [我方说明书.pdf ▼]                     │
│ [开始对比]                                            │
├─────────────────────────────────────────────────────┤
│ 对比历史                                              │
│ ┌─────┬──────────┬────────┬────────┬──────────┐    │
│ │ ID  │ 竞品文档 │ 我方文档│ 相似度 │ 时间     │    │
│ │ 1   │ v2.pdf   │ ours   │ 78%    │ 06-15    │    │
│ │ 2   │ v1.pdf   │ ours   │ 65%    │ 06-10    │    │
│ └─────┴──────────┴────────┴────────┴──────────┘    │
└─────────────────────────────────────────────────────┘
```

### 5.3 对比结果展示页面

**页面结构：**
```
┌─────────────────────────────────────────────────────┐
│ 对比结果 - 相似度 78%                                 │
├─────────────────────────────────────────────────────┤
│ [查看报告] [生成建议] [导出报告]                       │
├─────────────────────────────────────────────────────┤
│ 章节结构对比                                          │
│ ┌─────────────────────────────────────────────────┐ │
│ │ 竞品章节        │ 我方章节                        │ │
│ │ ├─ 产品介绍     │ ├─ 产品介绍 (✓匹配)             │ │
│ │ ├─ 技术参数     │ ├─ 技术规格 (⚠相似)             │ │
│ │ ├─ 使用方法     │ ├─ 操作指南 (✓匹配)             │ │
│ │ ├─ 故障排除     │ ✗ 我方缺失                      │ │
│ │ ✗ 竞品缺失      │ ├─ 常见问题                     │ │
│ └─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│ 内容差异列表                                          │
│ ┌─────┬────────┬──────────────────────────────┐    │
│ │ 章节│ 类型   │ 差异说明                       │    │
│ │ 参数│ 竞品独有│ 竞品包含IP68防水等级说明      │    │
│ │ 操作│ 内容差异│ 竞品描述更详细，多3个步骤     │    │
│ │ 故障│ 我方缺失│ 我方缺少故障排除章节         │    │
│ └─────┴────────┴──────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

---

## 六、开发计划

### 6.1 开发顺序

| 阶段 | 任务 | 预计时间 |
|------|------|---------|
| **Day 1-2** | 数据模型 + CRUD + API基础接口 | 2天 |
| **Day 3-4** | 文档上传 + 对比功能（复用现有引擎） | 2天 |
| **Day 5-6** | AI改进建议 + 报告生成 | 2天 |
| **Day 7-8** | 前端页面开发 | 2天 |
| **Day 9** | 前后端联调 + 测试 | 1天 |
| **Day 10** | 优化 + 文档 + 提交 | 1天 |

### 6.2 文件清单

**新增文件：**
```
backend/app/
├── models/competitor.py          # 数据模型
├── schemas/competitor.py         # Schema定义
├── crud/competitor.py            # CRUD操作
├── api/competitor.py             # API接口

frontend/src/
├── views/Competitor.vue          # 竞品管理页面
├── views/CompetitorCompare.vue   # 对比详情页面

backend/static/
├── competitor/                   # 竞品文档存储目录
```

**修改文件：**
```
backend/app/main.py               # 注册新路由
frontend/src/router/index.js      # 添加新路由
frontend/src/App.vue              # 添加侧边栏菜单项
frontend/src/api/index.js         # 添加API调用方法
```

---

## 七、接口详细设计

### 7.1 创建竞品

**请求：**
```json
POST /api/competitor
{
  "name": "XXX产品",
  "brand": "XXX品牌",
  "website": "https://www.xxx.com",
  "description": "竞品简介",
  "tags": "标签1,标签2"
}
```

**响应：**
```json
{
  "id": 1,
  "name": "XXX产品",
  "brand": "XXX品牌",
  "website": "https://www.xxx.com",
  "description": "竞品简介",
  "tags": "标签1,标签2",
  "created_at": "2026-06-29T10:00:00"
}
```

### 7.2 上传文档

**请求：**
```
POST /api/competitor/{id}/documents
Content-Type: multipart/form-data

file: 文档文件
doc_type: competitor / ours
version: v2.0
notes: 备注
```

**响应：**
```json
{
  "id": 1,
  "competitor_id": 1,
  "doc_type": "competitor",
  "file_name": "说明书v2.pdf",
  "file_path": "/static/competitor/xxx_v2.pdf",
  "file_type": "pdf",
  "version": "v2.0",
  "upload_date": "2026-06-29T10:00:00"
}
```

### 7.3 创建对比任务

**请求：**
```json
POST /api/competitor/{id}/compare
{
  "competitor_doc_id": 1,
  "our_doc_id": 2
}
```

**响应：**
```json
{
  "task_id": 1,
  "status": "pending",
  "message": "对比任务已创建，正在处理"
}
```

### 7.4 获取对比结果

**响应：**
```json
{
  "task_id": 1,
  "status": "completed",
  "similarity": 78.5,
  "result_data": {
    "structure_diff": [
      {"section": "产品介绍", "status": "match"},
      {"section": "技术参数", "status": "similar", "competitor_name": "技术参数", "our_name": "技术规格"},
      {"section": "故障排除", "status": "competitor_only"}
    ],
    "content_diff": [
      {"section": "技术参数", "type": "competitor_only", "content": "IP68防水等级说明"},
      {"section": "使用方法", "type": "content_diff", "detail": "竞品描述更详细，多3个步骤"}
    ],
    "chapter_similarity": [
      {"chapter": "产品介绍", "similarity": 95},
      {"chapter": "技术参数", "similarity": 72}
    ]
  },
  "created_at": "2026-06-29T10:00:00",
  "completed_at": "2026-06-29T10:02:00"
}
```

### 7.5 生成AI改进建议

**响应：**
```json
{
  "suggestions": [
    {
      "category": "内容补充",
      "content": "建议添加故障排除章节",
      "reason": "竞品说明书包含详细的故障排除指南，我方缺失此内容",
      "reference": "竞品故障排除章节包含10个常见问题及解决方案",
      "priority": "高"
    },
    {
      "category": "参数对标",
      "content": "建议补充IP68防水等级说明",
      "reason": "竞品明确标注IP68防水等级，我方未提及",
      "reference": "竞品原文：本产品支持IP68级防水...",
      "priority": "中"
    },
    {
      "category": "文案优化",
      "content": "建议扩充使用方法章节的步骤说明",
      "reason": "竞品的使用方法更详细，包含图示和注意事项",
      "reference": "竞品使用方法包含7个步骤，我方仅4个步骤",
      "priority": "中"
    }
  ],
  "generated_at": "2026-06-29T10:05:00"
}
```

---

## 八、报告模板设计

复用现有 `doc_report.py` 的HTML报告样式，新增以下内容：

1. **竞品vs我方对比报告标题**
2. **章节结构对比表**
3. **内容差异列表**
4. **AI改进建议区块**
5. **导出按钮**

---

## 九、技术要点

### 9.1 文档解析复用

直接调用 `doc_parser.py` 的 `compare_documents_by_format` 函数：
```python
from app.utils.doc_parser import compare_documents_by_format

result = compare_documents_by_format(
    doc_a_path=competitor_doc.file_path,
    doc_b_path=our_doc.file_path,
    format_a=competitor_doc.file_type,
    format_b=our_doc.file_type
)
```

### 9.2 AI建议生成

调用 `ai_client.py` 的对话接口：
```python
from app.utils.ai_client import AIClient

ai_client = AIClient()
prompt = f"分析对比结果并给出改进建议...\n对比数据: {result_data}"
suggestions = await ai_client.chat(prompt)
```

### 9.3 报告导出

复用 `doc_report.py` 的模板生成逻辑，保存为HTML文件供下载。

---

## 十、风险与对策

| 风险 | 对策 |
|------|------|
| 大文件上传耗时 | 限制文件大小（50MB），异步处理对比任务 |
| AI建议质量不稳定 | 精心设计Prompt，多次测试优化 |
| 前端页面复杂 | 分步开发，先做核心功能 |