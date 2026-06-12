# 团队协作开发指南

> 适用对象：**不会写代码的同事**，有 AI（Qwen/通义千问）帮忙写代码！

---

## 🎯 完整工作流程（4 步）

```
下载 ZIP → VS Code 打开 → Qwen 帮忙改代码 → 上传回 GitHub
```

---

## 📦 第 1 步：下载最新代码

### 每次开始工作前：

1. 打开 **https://github.com/caoyanyuan-glitch/smart-doc-platform**
2. 点击绿色按钮 **<> Code**
3. 点击 **Download ZIP**
4. 解压到 `C:\smart-doc-platform`

> 💡 **提示：** 每次开始新任务前都重新下载，确保拿到最新版本

---

## 💻 第 2 步：用 VS Code 打开项目

### 安装 VS Code（仅第一次）

1. 打开 **https://code.visualstudio.com/**
2. 点击绿色按钮 **Download for Windows**
3. 双击安装，一路边点"下一步"完成安装

### 用 VS Code 打开项目

1. 打开 VS Code
2. 点击左上角 **File（文件）** → **Open Folder（打开文件夹）**
3. 选择 `C:\smart-doc-platform` 文件夹
4. 点击 **选择文件夹**

✅ 现在你可以在 VS Code 里看到所有代码文件了！

---

## 🤖 第 3 步：用 Qwen（通义千问）帮忙改代码

### 打开 Qwen

1. 打开浏览器，访问：**https://qwen.ai** 或 **https://tongyi.aliyun.com**
2. 登录你的账号
3. 开始新对话

### 告诉 Qwen 你想做什么

**例子 1：想修改文档审核页面**
```
我想修改文档审核页面，文件路径是 frontend/src/views/Review.vue
帮我把页面标题改成"文档审核中心"，加一个"批量上传"按钮
```

**例子 2：想修改后端接口**
```
我想修改文档审核的后端接口，文件路径是 backend/app/api/review.py
帮我新增一个"导出报告"的功能
```

**例子 3：不知道在哪里改**
```
我想在首页加一个"使用说明"按钮，应该改哪个文件？
```

### Qwen 会告诉你：

1. 应该修改哪个文件
2. 具体改哪些代码
3. 怎么改

### 把 Qwen 说的代码复制到 VS Code

1. 在 VS Code 里打开 Qwen 告诉你的文件
2. 找到需要修改的位置
3. 复制 Qwen 给的代码，粘贴进去
4. 按 **Ctrl + S** 保存

---

## ⬆️ 第 4 步：把修改上传到 GitHub

### 方式 A：用 VS Code 上传（推荐）

1. 在 VS Code 左侧找到 **Source Control（源代码管理）** 图标（长得像分支的）
2. 你会看到所有修改过的文件（黄色或绿色）
3. 点击文件名旁边的 **+** 号，把文件加入暂存区
4. 在顶部的输入框里写清楚你做了什么修改：

```
张三：文档审核页面新增批量上传按钮
```

5. 点击上面的 **✓ Commit** 按钮（提交）
6. 点击 **Publish Branch**（发布分支）
7. 第一次可能要求你登录 GitHub，按提示操作即可

✅ 完成！你的修改已经上传到 GitHub 了！

---

### 方式 B：在 GitHub 网页上传

1. 打开 **https://github.com/caoyanyuan-glitch/smart-doc-platform**
2. 点击你想上传的文件（和 VS Code 里修改的一样）
3. 点击右上角 **✏️ 铅笔图标**
4. 把 VS Code 里修改后的代码**全部复制粘贴**到这里
5. 页面底部填写：

```
Commit changes
├── Commit title:（必填）
│   例如：张三：文档审核页面新增批量上传按钮
```

6. 点击 **Commit changes**

✅ 完成！

---

## 📋 每天的工作流程（汇总）

```
1. 下载最新 ZIP
   ↓
2. 用 VS Code 打开项目
   ↓
3. 打开 Qwen，告诉它你想做什么
   ↓
4. 把 Qwen 给的代码复制到 VS Code 对应文件
   ↓
5. 保存文件（Ctrl + S）
   ↓
6. 用 VS Code 或 GitHub 网页上传修改
   ↓
7. 启动项目测试效果
```

---

## 🔧 测试你改的代码

### 启动后端

打开**命令提示符**（Win键 + R，输入 cmd，回车）：

```cmd
cd C:\smart-doc-platform\backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 启动前端

再打开一个**命令提示符**窗口：

```cmd
cd C:\smart-doc-platform\frontend
npm install
npm run dev
```

### 查看效果

打开浏览器访问：`http://localhost:5173`

---

## 📁 文件位置对照表

### 前端文件（你可能需要修改的）

| 你想改什么 | 文件路径 |
|-----------|---------|
| 整个页面布局 | `frontend/src/App.vue` |
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

### 后端文件（可能需要修改的）

| 你想改什么 | 文件路径 |
|-----------|---------|
| 文档审核接口 | `backend/app/api/review.py` |
| 智能润色接口 | `backend/app/api/polish.py` |
| 智能问答接口 | `backend/app/api/qa.py` |
| 内容生成接口 | `backend/app/api/generate.py` |
| 文档对比接口 | `backend/app/api/compare.py` |
| 格式转换接口 | `backend/app/api/convert.py` |

---

## 🤖 怎么问 Qwen（通义千问）

### 模板 1：我想改界面

```
我想修改 [页面名称] 页面
文件路径：[文件路径]
需求：[具体想要什么效果]
```

**例子：**
```
我想修改文档审核页面
文件路径是 frontend/src/views/Review.vue
需求：把页面标题改成"文档审核中心"，加一个"批量上传"按钮
```

### 模板 2：我想加新功能

```
我想在 [模块] 里新增 [功能名称] 功能
文件路径：[文件路径]
请告诉我：
1. 需要修改哪些文件
2. 每个文件具体怎么改
3. 给出完整的代码
```

### 模板 3：不知道在哪里改

```
我想实现 [你想要的效果]
但不知道应该改哪个文件
请告诉我：
1. 需要修改哪个文件
2. 怎么改
3. 给出完整代码
```

---

## ⚠️ 注意事项

1. **每次开始工作前先下载最新 ZIP**，避免改到旧版本

2. **改之前告诉 Qwen 完整的文件路径**，这样它给的代码更准确

3. **保存文件后记得上传到 GitHub**，不然别人看不到你的修改

4. **上传时 commit message 要写清楚**，例如：
   - ✅ `张三：文档审核页面新增批量上传按钮`
   - ❌ `修改`

5. **不要删除或移动文件夹**，只修改文件内容

---

## ❓ 常见问题 FAQ

### Q1：Qwen 给的代码放哪里？

A：在 VS Code 里按 **Ctrl + P**，输入文件名找到文件，找到对应的位置粘贴，然后按 **Ctrl + S** 保存。

### Q2：改完后浏览器没变化？

A：按 **Ctrl + F5** 强制刷新浏览器，或者重启前端：
- 命令提示符按 **Ctrl + C** 停止
- 再输入 `npm run dev`

### Q3：不小心改错了怎么办？

A：在 VS Code 里按 **Ctrl + Z** 撤销，或者重新下载 ZIP。

### Q4：上传代码时要求登录 GitHub？

A：用你自己的 GitHub 账号登录，如果没有账号需要先注册。

### Q5：npm install 很慢？

A：在命令提示符里输入：
```cmd
npm config set registry https://registry.npmmirror.com
npm install
```

---

## 🚀 快速命令速查

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
| 张三 | 文档审核 | `Review.vue` + `review.py` |
| 李四 | 智能润色 | `Polish.vue` + `polish.py` |
| 王五 | 智能问答 | `QA.vue` + `qa.py` |
| 赵六 | 内容生成 | `Generate.vue` + `generate.py` |
| 陈七 | 文档对比 | `Compare.vue` + `compare.py` |
| 周八 | 格式转换 | `Convert.vue` + `convert.py` |

---

## 📞 遇到问题？

1. 把 **错误截图** 或 **Qwen 给的代码** 发给负责人
2. 负责人会帮你！

---

## ✅ 功能清单

- [x] 文档审核
- [x] 智能润色
- [x] 智能问答
- [x] 内容生成
- [x] 文档对比
- [x] 格式转换
- [x] 术语库管理
- [x] 用户管理

---

> 💡 **提示：** 把这个页面收藏起来，每次工作时按这个流程操作！
