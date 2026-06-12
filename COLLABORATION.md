# 团队协作开发指南

## 📋 目录

- [快速开始](#快速开始)
- [开发流程](#开发流程)
- [模块分工](#模块分工)
- [代码规范](#代码规范)
- [常见问题](#常见问题)

---

## 🚀 快速开始

### 方式一：每个人本地运行（推荐用于开发测试）

```bash
# 1. 解压最新版本
unzip smart-doc-platform-v1.1.3.zip
cd smart-doc-platform-v4

# 2. 启动后端（终端1）
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 启动前端（终端2）
cd ../frontend
npm install
npm run dev

# 4. 访问
# 浏览器打开 http://localhost:5173
```

### 方式二：一键启动脚本（Linux/Mac）

```bash
cd smart-doc-platform-v4
chmod +x start.sh
./start.sh
```

### 方式三：Windows 用户

```bat
# 后端
cd smart-doc-platform-v4\backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 另开终端 - 前端
cd smart-doc-platform-v4\frontend
npm install
npm run dev
```

---

## 📦 项目结构

```
smart-doc-platform-v4/
├── backend/                    # 后端 (Python + FastAPI)
│   ├── app/
│   │   ├── main.py          # 入口文件
│   │   ├── api/             # API路由（各模块独立）
│   │   │   ├── review.py       # 文档审核
│   │   │   ├── polish.py     # 润色
│   │   │   ├── qa.py         # 问答
│   │   │   ├── generate.py   # 内容生成
│   │   │   ├── compare.py    # 对比
│   │   │   ├── convert.py    # 格式转换
│   │   │   ├── rules.py      # 规则管理
│   │   │   ├── terms.py      # 术语库
│   │   │   └── auth.py       # 认证/用户
│   │   ├── crud/            # 数据库操作
│   │   ├── models/          # 数据模型
│   │   ├── schemas/         # 请求/响应结构
│   │   └── utils/           # 工具函数
│   └── requirements.txt       # Python依赖
│
├── frontend/                   # 前端 (Vue 3 + Vite)
│   ├── src/
│   │   ├── views/           # 页面组件（各模块独立）
│   │   │   ├── Home.vue       # 首页
│   │   │   ├── Review.vue     # 文档审核
│   │   │   ├── Polish.vue     # 润色
│   │   │   ├── QA.vue         # 问答
│   │   │   ├── Generate.vue   # 内容生成
│   │   │   ├── Compare.vue    # 对比
│   │   │   ├── Convert.vue    # 格式转换
│   │   │   ├── Terms.vue      # 术语库
│   │   │   ├── Rules.vue      # 规则管理
│   │   │   └── Users.vue     # 用户管理
│   │   ├── App.vue          # 主布局（左侧菜单）
│   │   ├── router/          # 路由配置
│   │   ├── api/             # API调用封装
│   │   └── main.js          # 入口文件
│   ├── vite.config.js       # Vite配置
│   └── package.json         # NPM依赖
│
└── start.sh                 # 一键启动脚本
└── COLLABORATION.md         # 本文件
```

---

## 👥 模块分工建议

### 推荐的分工方式

| 模块 | 负责人 | 文件 | 说明 |
|------|--------|------|
| **文档审核** | A | `backend/app/api/review.py` + `frontend/src/views/Review.vue` | 核心模块，文件上传、规则匹配、问题报告 |
| **智能润色** | B | `backend/app/api/polish.py` + `frontend/src/views/Polish.vue` | 文本优化、AI润色、前后文对比 |
| **智能问答** | C | `backend/app/api/qa.py` + `frontend/src/views/QA.vue` | 知识库、对话、问答系统 |
| **内容生成** | D | `backend/app/api/generate.py` + `frontend/src/views/Generate.vue` | 说明书生成、模板管理 |
| **文档对比** | E | `backend/app/api/compare.py` + `frontend/src/views/Compare.vue` | 双文档上传、差异分析 |
| **格式转换** | F | `backend/app/api/convert.py` + `frontend/src/views/Convert.vue` | Markdown/Word转DITA |
| **基础配置** | G | `backend/app/api/rules.py`、`terms.py`、`auth.py` | 规则/术语库/用户管理 |
| **UI/UX** | H | `App.vue`、`Home.vue` | 界面美化、统一风格 |

### 开发流程

```
1. 获取最新代码 → 2. 修改自己负责的模块 → 3. 本地测试 → 4. 提交修改 → 5. 打包分享
```

---

## 🛠 各模块开发指南

### 前端模块开发要点

#### 1. 新增API（后端）
```python
# 在 backend/app/api/[模块名].py

from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter()

@router.get("/")
async def get_items(db: Session = Depends(get_db)):
    # 你的逻辑
    return {"message": "Hello"}

# 然后在 backend/app/main.py 中注册
# app.include_router(router, prefix="/api/[模块名]", tags=["模块名"])
```

#### 2. 新增页面（前端）
```vue
<!-- 在 frontend/src/views/[模块名].vue -->
<template>
  <div class="your-container">
    <h2>页面标题</h2>
    <!-- 你的内容 -->
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { yourAPI } from '@/api'

const data = ref([])

onMounted(async () => {
  try {
    const response = await yourAPI.list()
    data.value = response.data
  } catch (e) {
    console.log('加载失败')
  }
})
</script>

<style>
.your-container {
  padding: 20px;
}
</style>
```

#### 3. 添加路由（在 `frontend/src/router/index.js`）
```javascript
{
  path: '/your-module',
  name: 'YourModule',
  component: () => import('@/views/YourModule.vue')
}
```

#### 4. 添加到菜单（在 `frontend/src/App.vue`）
```vue
<!-- 在 el-menu 中添加
<el-menu-item index="/your-module">
  <el-icon><Document /></el-icon>
  <template #title>你的模块</template>
</el-menu-item>
```

---

## 📝 API 调用方式

### 前端调用后端 API

所有 API 都通过 `frontend/src/api/index.js` 封装：

```javascript
// 1. 在 index.js 中添加你的 API
export const yourAPI = {
  list: () => instance.get('/your-module/'),
  create: (data) => instance.post('/your-module/', data),
  get: (id) => instance.get(`/your-module/${id}`),
  delete: (id) => instance.delete(`/your-module/${id}`)
}

// 2. 在页面中使用
import { yourAPI } from '@/api'

const response = await yourAPI.list()
```

### API 路径约定

- 列表: `GET /api/[模块名]/`
- 详情: `GET /api/[模块名]/{id}`
- 创建: `POST /api/[模块名]/`
- 更新: `PUT /api/[模块名]/{id}`
- 删除: `DELETE /api/[模块名]/{id}`

---

## 🎨 统一UI风格

### 颜色规范

| 用途 | 颜色 |
|------|------|
| 主色调 | #3b82f6（浅蓝色） |
| 强调色 | #2563eb（深蓝色） |
| 背景色 | #f5f7fa（浅灰） |
| 卡片背景 | #ffffff |
| 成功 | #10b981 |
| 警告 | #f59e0b |
| 错误 | #ef4444 |

### Element Plus 组件规范

- 表格: `<el-table>`
- 按钮: `<el-button type="primary">`
- 提示: `ElMessage.success('操作成功')`
- 对话框: `<el-dialog>`

---

## 🔄 测试流程

### 测试你的模块

```bash
# 后端测试
cd backend
# 直接用 curl 测试接口
curl http://localhost:8000/api/[你的模块]/

# 前端测试
cd ../frontend
npm run dev
# 浏览器访问测试页面
```

---

## ❓ 常见问题

### Q1: 端口被占用？

```bash
# Windows - 查找占用端口的进程
netstat -ano | findstr :8000
# 或使用其他端口
uvicorn app.main:app --port 8001

# 修改 vite 冲突时
npm run dev -- --port 5174
```

### Q2: Python 依赖安装慢？

```bash
# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q3: npm install 慢？

```bash
# 使用国内镜像
npm config set registry https://registry.npmmirror.com
npm install
```

### Q4: 前端修改后没生效？

```bash
# 清除缓存
cd frontend
rm -rf node_modules/.vite
npm run dev
```

### Q5: 如何添加新模块？

1. 后端：新建 `backend/app/api/[模块名].py
2. 在 `main.py` 中注册路由
3. 前端：新建 `frontend/src/views/[模块名].vue
4. 在 `router/index.js` 添加路由
5. 在 `App.vue` 添加菜单项
6. 在 `api/index.js` 添加API封装

---

## 📞 技术支持

如有问题，先检查：

1. 后端是否启动？访问 http://localhost:8000
2. 前端是否启动？访问 http://localhost:5173
3. 查看浏览器 Console 和终端输出
4. 查看后端终端输出

---

## ✅ 功能清单

- [x] 文档审核（上传文档 → 规则匹配 → 审核报告
- [x] 智能润色（文本输入 → AI润色 → 对比显示）
- [x] 智能问答（知识库选择 → 对话问答）
- [x] 内容生成（参数输入 → 生成文档）
- [x] 文档对比（双文档上传 → 差异分析）
- [x] 格式转换（Markdown → DITA）
- [x] 术语库（术语管理）
- [x] 用户管理（角色分配）
