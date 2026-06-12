# 智能技术文档平台

AI 驱动的文档审核、润色、问答、生成、对比与格式转换一站式解决方案。

## 🚀 一键启动（最简单！）

### 第 1 步：下载代码

访问 **https://github.com/caoyanyuan-glitch/smart-doc-platform**  
点击绿色 **<> Code** 按钮 → **Download ZIP** → 解压到 `C:\smart-doc-platform`

### 第 2 步：安装工具（仅第一次）

| 软件 | 下载地址 | 备注 |
|------|----------|------|
| Python | https://www.python.org/downloads/ | ⚠️ 安装时务必勾选 "Add Python to PATH" |
| Node.js | https://nodejs.org/ | 下载 LTS 版本 |

### 第 3 步：双击启动

**Windows 用户：**  
直接双击 `start.bat` 文件，等待自动完成即可！

**Mac/Linux 用户：**  
```bash
cd /path/to/smart-doc-platform
chmod +x start.sh
./start.sh
```

### 完成！

访问地址：**http://localhost:5173**

---

## 📖 详细教程

👉 请查阅 **[COLLABORATION.md](COLLABORATION.md)** 完整指南

包含：
- ✅ 完全用网页版 GitHub 修改代码（不用学命令！）
- ✅ 每个文件在哪个位置
- ✅ 常见问题解决
- ✅ 模块分工表

---

## 手动启动方式（高级用户）

如果一键脚本有问题，可以手动启动：

**终端 1（后端）：**
```cmd
cd C:\smart-doc-platform\backend
pip install -r requirements.txt
python init_data.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**终端 2（前端）：**
```cmd
cd C:\smart-doc-platform\frontend
npm install
npm run dev
```

---

## 功能模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 文档审核 | `Review.vue` + `review.py` | 上传文档 → 规则匹配 → 审核报告 |
| 智能润色 | `Polish.vue` + `polish.py` | 文本输入 → AI 润色 → 前后对比 |
| 智能问答 | `QA.vue` + `qa.py` | 选择知识库 → 对话式问答 |
| 内容生成 | `Generate.vue` + `generate.py` | 参数输入 → 生成文档 |
| 文档对比 | `Compare.vue` + `compare.py` | 双文档 → 差异高亮 |
| 格式转换 | `Convert.vue` + `convert.py` | 文档 → DITA/Markdown |

---

## 技术栈

- **后端：** Python 3.10+ / FastAPI / SQLAlchemy
- **前端：** Vue 3 / Vite / Element Plus
- **数据库：** SQLite（开发）