# 团队协作开发指南（超详细版）

> 适用对象：**零基础同事**，不需要学任何命令！

---

## 🌐 完全用网页版 GitHub（最简单！）

> 💡 **完全不需要安装任何软件！** 直接用浏览器就能修改代码！

### 第 1 步：在网页上打开文件

1. 打开浏览器，访问：**https://github.com/caoyanyuan-glitch/smart-doc-platform**
2. 点击 `frontend/src/views/` 文件夹
3. 点击你想修改的文件，例如 `Review.vue`（文档审核页面）

### 第 2 步：修改代码

1. 点击页面右上角的 **✏️ 铅笔图标**
2. 在浏览器里直接修改代码
3. 改完后，页面底部填写：

```
Commit changes
├── Commit title:（必填，写你改了什么）
│   例如：张三：文档审核页面新增上传按钮
│
└── Extended description:（可选，简单描述）
```

4. 点击绿色的 **Commit changes** 按钮

5. ✅ 你的修改已经保存到 GitHub 了！

### 第 3 步：下载最新代码到本地测试

**方法 A（推荐）：重新下载 ZIP**

1. 删除 `C:\smart-doc-platform` 文件夹里的所有文件
2. 回到 GitHub 仓库页面，点击绿色 **<> Code** 按钮
3. 点击 **Download ZIP**
4. 解压到 `C:\smart-doc-platform` 文件夹

**方法 B：只下载你改过的文件**

1. 在 GitHub 上进入你改过的文件
2. 点击右上角 **下载图标**（Raw）
3. 浏览器会打开纯文本内容，右键保存到本地对应位置

### 第 4 步：运行项目看效果

打开**命令提示符**（Win键 + R，输入 cmd，回车）：

```cmd
cd C:\smart-doc-platform\backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**再打开一个命令提示符窗口**：

```cmd
cd C:\smart-doc-platform\frontend
npm install
npm run dev
```

打开浏览器访问：`http://localhost:5173`

### 第 5 步：通知负责人

效果 OK 后，告诉负责人你改了哪些文件，让他审核合并到正式版本。

---

### 🌐 网页版能做的所有事情

| 你想做什么 | 在哪里操作 |
|-----------|-----------|
| 查看某个文件 | 点击文件名即可 |
| 修改代码 | 点右上角 ✏️ 铅笔图标 |
| 新建文件 | 点击 `Add file` → `Create new file` |
| 创建文件夹 | 新建文件时，文件名写 `文件夹名/文件名` |
| 删除文件 | 进入文件 → 点右上角垃圾桶图标 |
| 重命名文件 | 进入文件 → 点右上角 ✏️ → 修改文件名 |
| 查看历史修改 | 进入文件 → 点右上角 ⏱️ History |

---

## 🌳 项目文件位置（对照表）

| 你想修改 | 文件路径 |
|---------|---------|
| 首页布局 | `frontend/src/App.vue` |
| 首页内容 | `frontend/src/views/Home.vue` |
| 文档审核页面 | `frontend/src/views/Review.vue` |
| 智能润色页面 | `frontend/src/views/Polish.vue` |
| 智能问答页面 | `frontend/src/views/QA.vue` |
| 内容生成页面 | `frontend/src/views/Generate.vue` |
| 文档对比页面 | `frontend/src/views/Compare.vue` |
| 格式转换页面 | `frontend/src/views/Convert.vue` |
| 术语库页面 | `frontend/src/views/Terms.vue` |
| 规则管理页面 | `frontend/src/views/Rules.vue` |
| 用户管理页面 | `frontend/src/views/Users.vue` |
| API 调用封装 | `frontend/src/api/index.js` |
| 左侧菜单配置 | `frontend/src/App.vue`（底部 el-menu 部分） |

| 你想修改（后端） | 文件路径 |
|-----------------|---------|
| 文档审核接口 | `backend/app/api/review.py` |
| 智能润色接口 | `backend/app/api/polish.py` |
| 智能问答接口 | `backend/app/api/qa.py` |
| 内容生成接口 | `backend/app/api/generate.py` |
| 文档对比接口 | `backend/app/api/compare.py` |
| 格式转换接口 | `backend/app/api/convert.py` |

---

## 🌳 完整目录结构

```
smart-doc-platform/
│
├── backend/              ← Python 后端
│   ├── app/
│   │   ├── main.py          入口文件
│   │   ├── api/             API 接口
│   │   │   ├── review.py      文档审核
│   │   │   ├── polish.py      智能润色
│   │   │   ├── qa.py          智能问答
│   │   │   ├── generate.py    内容生成
│   │   │   ├── compare.py     文档对比
│   │   │   └── convert.py     格式转换
│   │   ├── crud/            数据库操作
│   │   ├── models/          数据模型
│   │   ├── schemas/         请求/响应格式
│   │   └── utils/           工具函数
│   └── requirements.txt     Python 依赖
│
└── frontend/              ← Vue 前端
    ├── src/
    │   ├── main.js          入口文件
    │   ├── App.vue          主布局（左侧菜单）
    │   ├── router/          路由配置
    │   ├── api/             API 调用封装
    │   ├── store/           状态管理
    │   └── views/           页面组件
    │       ├── Home.vue       首页
    │       ├── Review.vue     文档审核
    │       ├── Polish.vue     智能润色
    │       ├── QA.vue         智能问答
    │       ├── Generate.vue   内容生成
    │       ├── Compare.vue    文档对比
    │       ├── Convert.vue    格式转换
    │       ├── Terms.vue      术语库
    │       ├── Rules.vue      规则管理
    │       └── Users.vue      用户管理
    └── package.json         NPM 依赖
```

---

## 🚀 启动项目（本地测试用）

### 需要安装的软件

| 软件 | 下载地址 | 用途 |
|------|----------|------|
| Python | https://www.python.org/downloads/ | 运行后端（⚠️ 安装时勾选 "Add Python to PATH"） |
| Node.js | https://nodejs.org/ | 运行前端 |

### 启动命令

**终端 1（后端）：**
```cmd
cd C:\smart-doc-platform\backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**终端 2（前端）：**
```cmd
cd C:\smart-doc-platform\frontend
npm install
npm run dev
```

**访问地址：** http://localhost:5173

---

## 🔄 获取最新代码

### 方法 A（推荐）：重新下载 ZIP

1. 删除本地 `C:\smart-doc-platform` 里的所有文件
2. GitHub 仓库页面 → 点 **<> Code** → **Download ZIP**
3. 解压覆盖

### 方法 B：只下载改过的文件

1. 在 GitHub 上找到你改过的文件
2. 点右上角下载图标
3. 保存到本地对应位置

---

## ⚠️ 注意事项

1. **不要直接改 main 分支！** 所有人都在自己分支上改，然后通知负责人合并

2. **commit message 要写清楚**！例如：
   - ✅ `张三：文档审核页面新增上传按钮`
   - ❌ `修改代码`

3. **修改前先在 GitHub 上看最新的代码**，避免改到旧版本

4. **改完后下载到本地测试**，确认效果 OK 再通知负责人

---

## ❓ 常见问题 FAQ

### Q1：`pip install` 很慢？

使用国内镜像：
```cmd
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q2：`npm install` 很慢？

```cmd
npm config set registry https://registry.npmmirror.com
npm install
```

### Q3：端口 8000 被占用？

换一个端口：
```cmd
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

然后修改前端文件 `frontend/src/api/index.js`，把 `localhost:8000` 改成 `localhost:8001`

### Q4：浏览器显示空白？

1. 按 **F5** 或 **Ctrl + F5** 强制刷新
2. 检查后端和前端终端是否都在运行
3. 按 **F12** 查看 Console 是否有红色错误

### Q5：修改后没效果？

1. 按 **Ctrl + F5** 强制刷新浏览器
2. 或者重启前端：
   - 前端终端按 **Ctrl + C** 停止
   - 再输入 `npm run dev` 重新启动

---

## 🎯 快速命令速查

### 启动后端
```cmd
cd C:\smart-doc-platform\backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 启动前端
```cmd
cd C:\smart-doc-platform\frontend
npm install
npm run dev
```

### 访问地址
```
http://localhost:5173
```

---

## 👥 模块分工（建议）

| 负责人 | 模块 | 文件 |
|--------|------|------|
| 张三 | 文档审核 | `backend/app/api/review.py` + `frontend/src/views/Review.vue` |
| 李四 | 智能润色 | `backend/app/api/polish.py` + `frontend/src/views/Polish.vue` |
| 王五 | 智能问答 | `backend/app/api/qa.py` + `frontend/src/views/QA.vue` |
| 赵六 | 内容生成 | `backend/app/api/generate.py` + `frontend/src/views/Generate.vue` |
| 陈七 | 文档对比 | `backend/app/api/compare.py` + `frontend/src/views/Compare.vue` |
| 周八 | 格式转换 | `backend/app/api/convert.py` + `frontend/src/views/Convert.vue` |

---

## 📞 遇到问题？

1. 把 **错误截图** 或 **终端里的红色文字** 发给负责人
2. 负责人会帮你解决！

---

## ✅ 功能清单

- [x] 文档审核（上传文档 → 规则匹配 → 审核报告）
- [x] 智能润色（文本输入 → AI 润色 → 前后文对比）
- [x] 智能问答（选择知识库 → 对话式问答）
- [x] 内容生成（参数输入 → 生成说明书/文档）
- [x] 文档对比（双文档上传 → 差异高亮）
- [x] 格式转换（上传文档 → DITA/Markdown）
- [x] 术语库管理
- [x] 用户管理

---

> 💡 **提示：** 把这个页面收藏起来，遇到问题随时查阅！
