# 智能技术文档平台

AI 驱动的文档审核、润色、问答、生成、对比与格式转换一站式解决方案。

## 🚀 快速开始（3 步运行）

### 第 1 步：下载代码

**方式 A（最简单）：下载 ZIP 包**

访问仓库页面 → 点击绿色 **<> Code** 按钮 → 点击 **Download ZIP** → 解压到 `C:\smart-doc-platform`

**方式 B（装了 Git）：克隆仓库**
```cmd
git clone https://github.com/caoyanyuan-glitch/smart-doc-platform.git
```

### 第 2 步：安装工具（仅第一次）

| 工具 | 下载地址 | 用途 |
|------|----------|------|
| Python | https://www.python.org/downloads/ | 运行后端 |
| Node.js | https://nodejs.org/ | 运行前端 |
| VS Code | https://code.visualstudio.com/ | 编辑代码（可选） |

> ⚠️ 安装 Python 时**务必勾选** "Add Python to PATH"

### 第 3 步：启动项目

**打开终端 1（后端）：**
```cmd
cd C:\smart-doc-platform\backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**打开终端 2（前端）：**
```cmd
cd C:\smart-doc-platform\frontend
npm install
npm run dev
```

**打开浏览器：** 访问 `http://localhost:5173`

---

## 📖 详细使用教程

**👉 请查阅 [COLLABORATION.md](COLLABORATION.md) 完整指南**

包含：
- ✅ Windows 每一步操作截图说明
- ✅ 命令行输入示范
- ✅ 常见问题解决（8 个 FAQ）
- ✅ Git 入门教程
- ✅ 模块分工说明

---

## 功能模块

| 模块 | 文件路径 | 功能描述 |
|------|----------|----------|
| **文档审核** | `backend/app/api/review.py` + `frontend/src/views/Review.vue` | 上传文档 → 规则匹配 → 审核报告 |
| **智能润色** | `backend/app/api/polish.py` + `frontend/src/views/Polish.vue` | 文本输入 → AI 润色 → 前后对比 |
| **智能问答** | `backend/app/api/qa.py` + `frontend/src/views/QA.vue` | 选择知识库 → 对话式问答 |
| **内容生成** | `backend/app/api/generate.py` + `frontend/src/views/Generate.vue` | 参数输入 → 生成说明书/文档 |
| **文档对比** | `backend/app/api/compare.py` + `frontend/src/views/Compare.vue` | 双文档上传 → 差异高亮 |
| **格式转换** | `backend/app/api/convert.py` + `frontend/src/views/Convert.vue` | 上传文档 → DITA/Markdown |

---

## 项目结构

```
smart-doc-platform/
├── backend/              Python 后端 (FastAPI)
│   ├── app/
│   │   ├── main.py       入口文件
│   │   ├── api/          API 接口（各模块独立）
│   │   ├── crud/         数据库操作
│   │   └── database.py   数据库配置
│   └── requirements.txt  依赖列表
│
└── frontend/              Vue 3 前端 (Vite + Element Plus)
    ├── src/
    │   ├── App.vue       主布局（左侧菜单）
    │   ├── views/        页面组件（各模块独立）
    │   ├── api/          API 调用封装
    │   └── main.js       入口文件
    └── package.json      NPM 依赖
```

---

## 技术栈

- **后端：** Python 3.10+ / FastAPI / SQLAlchemy / Uvicorn
- **前端：** Vue 3 / Vite / Element Plus / Axios
- **数据库：** SQLite（开发）可切换 PostgreSQL/MySQL（生产）
