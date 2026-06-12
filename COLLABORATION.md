# 团队协作开发指南（超详细版）

> 适用对象：**零基础同事**，不会用 Git/GitHub 也没关系！

---

## 📦 方式一：下载 ZIP 包（最简单，推荐小白）

### 第 1 步：打开 GitHub 仓库

在浏览器打开：**https://github.com/caoyanyuan-glitch/smart-doc-platform**

### 第 2 步：下载 ZIP 包

1. 点击页面中间偏右的绿色按钮 **<> Code**
2. 在弹出的菜单最底部，点击 **Download ZIP**
3. 浏览器开始下载文件 `smart-doc-platform-main.zip`

### 第 3 步：解压文件

**Windows 用户：**

1. 在下载目录找到 `smart-doc-platform-main.zip`
2. 右键点击文件 → **"全部提取"**（或用 7-Zip / 解压到当前文件夹）
3. 选择解压位置，例如 `C:\smart-doc-platform`
4. 点击 **"提取"**

**解压后目录结构：**

```
smart-doc-platform-main/
├── backend/          ← Python 后端
│   ├── app/
│   └── requirements.txt
└── frontend/          ← Vue 前端
    ├── src/
    └── package.json
```

---

## 🛠️ 安装必要的工具

### Windows 用户需要安装 3 个软件

---

### 🔧 1. 安装 Python（后端运行环境）

**下载地址：** https://www.python.org/downloads/

1. 点击黄色按钮 **"Download Python 3.x.x"**
2. 双击下载的安装包 `python-3.x.x-amd64.exe`
3. **⚠️ 非常重要：勾选 "Add Python.exe to PATH"**（安装界面最下方的复选框）
4. 点击 **Install Now**
5. 等待安装完成（约 1-2 分钟）

**验证安装：**

打开 **命令提示符**（Win 键 + R，输入 `cmd` 回车）：

```
python --version
```

应该显示：`Python 3.x.x`

---

### 🔧 2. 安装 Node.js（前端运行环境）

**下载地址：** https://nodejs.org/

1. 点击绿色按钮 **"20.x.x LTS"** 下载
2. 双击安装包 `node-v20.x.x-x64.msi`
3. 一路点击 **Next**（使用默认设置）
4. 点击 **Install** → 等待安装完成
5. 安装完成后可能需要**重启电脑**

**验证安装：**

打开新的命令提示符窗口：

```
node --version
```

应该显示：`v20.x.x`

```
npm --version
```

应该显示：`10.x.x`

---

### 🔧 3. 安装 VS Code（代码编辑器，可选但推荐）

**下载地址：** https://code.visualstudio.com/

1. 点击 **Download for Windows**
2. 双击安装包 `VSCodeUserSetup-x64-x.x.x.exe`
3. 一路点击 **下一步**
4. 勾选 **"添加到 PATH"** 选项（默认已勾选）
5. 点击 **安装**

> ⚠️ 不装 VS Code 也可以，用记事本或其他编辑器也行

---

## 🚀 启动项目（Windows 详细步骤）

### 第 1 步：打开两个命令提示符窗口

按 **Win 键**，输入 `cmd`，回车，**打开两次**（需要两个终端）

你会看到：
```
C:\Users\你的用户名>_
```

### 第 2 步：在终端 1 启动后端

```cmd
# 1. 进入项目目录（根据你的解压位置调整）
cd C:\smart-doc-platform\smart-doc-platform-main\backend

# 2. 安装 Python 依赖（第一次需要几分钟）
pip install -r requirements.txt

# 3. 启动后端服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

✅ **成功标志：** 终端显示类似以下内容，并且光标在底部闪烁：
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**⚠️ 保持这个终端窗口打开，不要关闭！**

---

### 第 3 步：在终端 2 启动前端

打开另一个新的命令提示符窗口：

```cmd
# 1. 进入前端目录
cd C:\smart-doc-platform\smart-doc-platform-main\frontend

# 2. 安装前端依赖（第一次需要 3-5 分钟，耐心等待）
npm install

# 3. 启动前端服务
npm run dev
```

✅ **成功标志：** 终端显示类似：
```
  VITE v5.x.x  ready in 500 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
```

**⚠️ 保持这个终端窗口打开，不要关闭！**

---

### 第 4 步：访问应用

打开浏览器（Chrome/Edge 都可以），访问：

```
http://localhost:5173
```

你应该看到：**智能技术文档平台**的首页！

---

## 🌳 项目目录说明

```
smart-doc-platform-main/
│
├── backend/              ← Python 后端
│   ├── app/
│   │   ├── main.py          入口文件（启动时读取）
│   │   ├── api/             API 接口（各模块独立）
│   │   │   ├── review.py      文档审核
│   │   │   ├── polish.py      智能润色
│   │   │   ├── qa.py          智能问答
│   │   │   ├── generate.py    内容生成
│   │   │   ├── compare.py     文档对比
│   │   │   └── convert.py     格式转换
│   │   ├── crud/            数据库操作
│   │   ├── models/          数据模型
│   │   ├── schemas/         请求/响应格式
│   │   ├── utils/           工具函数
│   │   └── database.py      数据库配置
│   └── requirements.txt     Python 依赖列表
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
    │       └── Convert.vue    格式转换
    └── package.json         NPM 依赖和脚本
│
├── README.md              项目简介
└── COLLABORATION.md       本文件（团队协作指南）
```

---

## 👨‍💻 各模块负责人分工建议

| 模块 | 文件路径 | 功能描述 |
|------|----------|----------|
| **文档审核** | `backend/app/api/review.py` + `frontend/src/views/Review.vue` | 上传文档 → 规则匹配 → 生成审核报告 |
| **智能润色** | `backend/app/api/polish.py` + `frontend/src/views/Polish.vue` | 输入文本 → AI 润色 → 前后对比 |
| **智能问答** | `backend/app/api/qa.py` + `frontend/src/views/QA.vue` | 选择知识库 → 提问 → 获取答案 |
| **内容生成** | `backend/app/api/generate.py` + `frontend/src/views/Generate.vue` | 输入参数 → 生成说明书/文档 |
| **文档对比** | `backend/app/api/compare.py` + `frontend/src/views/Compare.vue` | 上传两个文档 → 高亮差异 |
| **格式转换** | `backend/app/api/convert.py` + `frontend/src/views/Convert.vue` | 上传文档 → 转换为 DITA/Markdown |

---

## 🔧 修改某个模块的步骤（举例：修改文档审核）

### 第 1 步：停止前端服务

在前端终端窗口，按 **Ctrl + C**（不需要停止后端）

### 第 2 步：打开文件

用 VS Code 或记事本打开：

```
C:\smart-doc-platform\smart-doc-platform-main\frontend\src\views\Review.vue
```

### 第 3 步：修改代码

比如修改页面标题、添加按钮等

### 第 4 步：保存文件

按 **Ctrl + S** 保存

### 第 5 步：重启前端

```cmd
cd C:\smart-doc-platform\smart-doc-platform-main\frontend
npm run dev
```

浏览器访问 `http://localhost:5173` 查看效果。

> 💡 **小技巧：** 前端支持热更新，大多数修改**不需要重启**，保存后浏览器自动刷新！

---

## 🔧 修改后端代码

### 第 1 步：停止后端服务

在后端终端窗口，按 **Ctrl + C**

### 第 2 步：打开文件

用 VS Code 或记事本打开：

```
C:\smart-doc-platform\smart-doc-platform-main\backend\app\api\review.py
```

### 第 3 步：修改代码并保存

### 第 4 步：重启后端

```cmd
cd C:\smart-doc-platform\smart-doc-platform-main\backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> 💡 **小技巧：** 加了 `--reload` 参数后，**大多数修改不需要重启**，保存后后端自动重新加载！

---

## 🔄 获取最新代码（项目负责人更新代码后）

### 方式 A：重新下载 ZIP（最简单）

1. 访问 https://github.com/caoyanyuan-glitch/smart-doc-platform
2. 点击 **Code** → **Download ZIP**
3. 删除旧的项目目录
4. 解压新的 ZIP 到同一路径

### 方式 B：使用 Git（学会了更方便）

详见下方 Git 教程

---

## 📚 Git 入门教程（可选，但学会了更高效）

### 第 1 步：安装 Git

**下载地址：** https://git-scm.com/download/win

1. 下载 `64-bit Git for Windows Setup`
2. 双击安装，一路 **Next**（全部用默认设置）
3. 安装完成后，在桌面右键应该能看到 **"Git Bash Here"** 选项

**验证安装：** 打开新的命令提示符，输入：
```
git --version
```
应该显示：`git version 2.x.x`

### 第 2 步：克隆项目（第一次使用）

```cmd
cd C:\
git clone https://github.com/caoyanyuan-glitch/smart-doc-platform.git
cd smart-doc-platform
```

✅ 现在你有了项目的最新代码

### 第 3 步：获取最新代码（每天上班前）

```cmd
cd C:\smart-doc-platform
git pull
```

### 第 4 步：提交你的修改（修改完成后）

```cmd
# 查看改了哪些文件
git status

# 添加所有修改
git add .

# 提交修改（写清楚你改了什么）
git commit -m "文档审核模块：新增批量上传功能"

# 推送到 GitHub
git push
```

> ⚠️ 推送（`git push`）需要 Token，联系项目负责人获取

---

## ❓ 常见问题 FAQ

### Q1：`pip install` 很慢或报错？

**解决方案：** 使用国内镜像源

```cmd
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

或者设置默认镜像：
```cmd
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### Q2：`npm install` 很慢或报错？

**解决方案：** 使用国内镜像源

```cmd
npm config set registry https://registry.npmmirror.com
npm install
```

---

### Q3：端口 8000 或 5173 被占用？

**解决方案：**

1. 关闭之前打开的终端窗口
2. 或者用其他端口：

```cmd
# 后端换端口
uvicorn app.main:app --host 0.0.0.0 --port 8001

# 前端换端口（在 vite.config.js 中修改，或运行时指定）
npm run dev -- --port 5174
```

---

### Q4：`uvicorn` 不是内部或外部命令？

**解决方案：** 用 Python 模块方式运行

```cmd
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

### Q5：`'npm' 不是内部或外部命令`？

**解决方案：** Node.js 没安装或需要重启电脑

1. 确认已安装 Node.js
2. 重启电脑
3. 重新打开命令提示符

---

### Q6：浏览器访问 http://localhost:5173 空白？

**排查步骤：**

1. ✅ 检查后端终端是否在运行（显示 `Uvicorn running on http://0.0.0.0:8000`）
2. ✅ 检查前端终端是否在运行（显示 `VITE ready in xxx ms`）
3. ✅ 刷新浏览器（F5 或 Ctrl + F5 强制刷新）
4. ✅ 按 F12 打开开发者工具，查看 Console 是否有红色错误

---

### Q7：修改代码后浏览器没变化？

**解决方案：**

1. 浏览器按 **Ctrl + F5** 强制刷新
2. 或者前端终端按 **Ctrl + C** 停止后重新 `npm run dev`

---

### Q8：Python 依赖安装报错缺少 Microsoft Visual C++？

**解决方案：** 安装 Build Tools

下载地址：https://visualstudio.microsoft.com/visual-cpp-build-tools/

安装时勾选 **"Desktop development with C++"**

---

## 📞 遇到问题怎么办？

1. **查看终端输出** - 后端和前端终端都会显示错误信息（红色文字）
2. **查看浏览器 Console** - 按 F12，点击 Console 标签
3. **把错误信息截图发给负责人** - 帮助快速定位问题
4. **重启服务** - 按 Ctrl+C 停止，再重新启动

---

## 🎯 快速命令速查卡（贴在显示器旁）

### 后端启动命令
```cmd
cd C:\smart-doc-platform\backend
pip install -r requirements.txt      （仅第一次）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端启动命令
```cmd
cd C:\smart-doc-platform\frontend
npm install                           （仅第一次）
npm run dev
```

### 访问地址
```
浏览器打开：http://localhost:5173
```

### 获取最新代码
```cmd
cd C:\smart-doc-platform
git pull                              （装了 Git 后）
```

---

## ✅ 功能清单

- [x] 文档审核（上传文档 → 规则匹配 → 审核报告）
- [x] 智能润色（文本输入 → AI 润色 → 前后文对比显示）
- [x] 智能问答（选择知识库 → 对话式问答）
- [x] 内容生成（参数输入 → 生成说明书/文档）
- [x] 文档对比（双文档上传 → 差异高亮显示）
- [x] 格式转换（上传文档 → 转换为 DITA/Markdown）
- [x] 术语库管理（在内容生成子菜单中）
- [x] 用户管理（角色分配管理）

---

> 💡 **提示：** 把这个页面收藏起来，遇到问题随时查阅！
