# 团队协作开发指南

> **你不需要会写代码！** VS Code 里的 AI 助手会直接帮你改代码！

---

## 🎯 工作流程（只需要 3 步）

```
第1步：下载 ZIP 到本地
    ↓
第2步：用 VS Code 打开，让 AI 助手改代码
    ↓
第3步：让 AI 助手帮你上传到 GitHub
```

---

## 📦 第 1 步：下载最新代码到本地

1. 打开 **https://github.com/caoyanyuan-glitch/smart-doc-platform**
2. 点击绿色按钮 **<> Code**
3. 点击 **Download ZIP**
4. 解压到 `C:\smart-doc-platform`（注意：每次开始新任务前都要重新下载，确保是最新版本）

---

## 💻 第 2 步：用 VS Code 打开项目

### 安装 VS Code 和 AI 助手（联系 IT）

⚠️ **VS Code 和 AI 助手需要联系 IT 安装，请按团队流程处理。**

### 打开项目

1. 打开 VS Code
2. 点左上角 **File（文件）** → **Open Folder（打开文件夹）**
3. 选择 `C:\smart-doc-platform`，点 **选择文件夹**

✅ 好了！你现在可以看到所有代码了！

---

## 第 3 步：让 VS Code 里的 AI 助手帮你写代码和上传

### 打开 AI 助手插件

1. 在 VS Code 左侧找到 AI 助手图标
2. 打开 AI 助手聊天窗口

### 告诉 AI 助手你想做什么

**例子 1：修改代码**
```
我想修改文档审核页面，文件路径是 frontend/src/views/Review.vue
帮我把页面标题改成"文档审核中心"
```

**例子 2：改完代码后让 AI 助手上传**
```
帮我把刚才的修改上传到 GitHub，commit message 写"张三：修改文档审核页面标题"
```

**你不需要自己写代码！也不需要自己上传！AI 助手会帮你完成。**

### AI 助手自动修改代码并上传

1. AI 助手理解你的需求后，会自动显示修改后的代码
2. 点击 **Apply**（应用）按钮，代码就自动改好了！
3. 接着在 AI 助手里说"帮我上传到 GitHub"，AI 助手会自动执行上传。

就这么简单！你只需要描述需求，AI 助手会协助完成。

---

## 📋 每天的工作流程

```
1. 打开 GitHub，下载最新 ZIP
    ↓
2. 用 VS Code 打开，让 AI 助手改代码
    ↓
3. 让 AI 助手帮你上传到 GitHub
```

---

## 🔧 测试你改的代码

### 启动后端

打开命令提示符（Win + R，输入 cmd，回车）：

```cmd
cd C:\smart-doc-platform\backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 启动前端

再打开一个命令提示符窗口：

```cmd
cd C:\smart-doc-platform\frontend
npm install
npm run dev
```

### 查看效果

打开浏览器访问：`http://localhost:5173`

---

## 🔍 审核和合并代码（负责人操作）

### 第1步：查看所有人的修改

1. 打开 **https://github.com/caoyanyuan-glitch/smart-doc-platform**
2. 点击顶部的 **Commits** 标签
3. 可以看到所有人提交的修改记录

### 第2步：测试所有人的代码

1. 点击绿色按钮 **<> Code** → **Download ZIP**
2. 解压到 `C:\smart-doc-platform`（覆盖旧文件）
3. 按照上面的步骤启动前后端
4. 测试所有功能是否正常

### 第3步：合并代码（如有冲突）

如果多人修改了同一个文件，可能会有冲突，让 AI 助手帮你处理：

1. 在 VS Code 里打开项目
2. 打开 AI 助手插件
3. 告诉 AI 助手：
```
帮我查看并解决 GitHub 上的代码冲突
```

AI 助手会帮你分析冲突并合并代码。

### 第4步：更新到主分支

让 AI 助手帮你把所有修改合并到主分支：

```
帮我把所有修改合并到 main 分支
```

---

## 常用文件路径（告诉 AI 助手用）

| 你想改什么 | 文件路径 |
|-----------|---------|
| 左侧菜单/整体布局 | `frontend/src/App.vue` |
| 首页 | `frontend/src/views/Home.vue` |
| 文档审核 | `frontend/src/views/Review.vue` |
| 智能润色 | `frontend/src/views/Polish.vue` |
| 智能问答 | `frontend/src/views/QA.vue` |
| 内容生成 | `frontend/src/views/Generate.vue` |
| 文档对比 | `frontend/src/views/Compare.vue` |
| 格式转换 | `frontend/src/views/Convert.vue` |

---

## 怎么问 AI 助手

直接告诉它你想做什么就行！**你不需要懂代码！**

**模板 1：修改代码**
```
我想修改 [页面名称]
文件路径：[上面表格里的路径]
需求：[你想要什么效果]
```

**模板 2：上传到 GitHub**
```
帮我把刚才的修改上传到 GitHub，commit message 写"张三：修改了xxx"
```

**例子：**
```
我想修改文档审核页面
文件路径是 frontend/src/views/Review.vue
需求：把页面标题改成"文档审核中心"，加一个"批量上传"按钮
```

AI 助手会自动改好代码，你只需要点击 Apply。改完后再让 AI 助手上传到 GitHub。

---

## ⚠️ 注意事项

1. **每次开始前先下载最新 ZIP**，避免改到旧版本
2. **告诉 AI 助手完整的文件路径**，它才能给你准确的代码
3. **改完记得上传到 GitHub**，不然别人看不到
4. **commit 信息要写清楚**：`张三：xxx`

---

## ❓ 常见问题

**Q1：AI 助手在哪里？**
A：在 VS Code 左侧找到 AI 助手图标，点击打开对应插件。

**Q2：改完后浏览器没变化？**
A：按 **Ctrl + F5** 强制刷新。

**Q3：不小心改错了？**
A：按 **Ctrl + Z** 撤销，或者重新下载 ZIP。

**Q4：npm install 很慢？**
A：输入 `npm config set registry https://registry.npmmirror.com` 再重试。

---

> **记住：你只需要描述需求并确认修改，AI 助手会协助完成开发和上传。**
