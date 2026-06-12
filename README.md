# 智能技术文档平台

AI 驱动的文档审核、润色、问答、生成、对比与格式转换一站式解决方案。

## 功能模块

- **智能润色** - 文本优化、AI润色、前后文对比
- **内容生成** - 基于参数和模板生成标准化文档
- **文档对比** - 智能对比两个版本文档的差异
- **格式转换** - Word/Markdown 转 DITA 结构化文档
- **文档审核** - 规则+AI双重审核，问题跟踪和报告导出
- **智能问答** - 基于知识库的对话式问答

## 快速开始

### 后端启动

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

### 访问

浏览器打开 http://localhost:5173

## 项目结构

```
smart-doc-platform-v4/
├── backend/           # Python FastAPI 后端
│   └── app/
│       ├── api/       # API路由（各模块独立文件）
│       ├── crud/      # 数据库操作
│       └── main.py    # 入口文件
└── frontend/          # Vue 3 + Vite 前端
    └── src/
        ├── views/     # 页面组件（各模块独立文件）
        ├── App.vue    # 主布局
        └── api/       # API调用封装
```

## 团队协作

详见 [COLLABORATION.md](COLLABORATION.md)

## 技术栈

- 后端：Python 3.10+ / FastAPI / SQLAlchemy
- 前端：Vue 3 / Vite / Element Plus
- 数据库：SQLite（开发）/ PostgreSQL（生产）