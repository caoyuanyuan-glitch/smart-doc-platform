# 团队协作开发指南

> **你不需要会写代码！** 只需要下载 → 复制粘贴 → 上传，Qwen 会帮你写代码！

---

## 🎯 工作流程（只需要 4 步）

```
第1步：下载 ZIP 到本地
    ↓
第2步：用 VS Code 打开
    ↓
第3步：问 Qwen，复制它给的代码到 VS Code
    ↓
第4步：上传到 GitHub
```

---

## 📦 第 1 步：下载最新代码到本地

1. 打开 **https://github.com/caoyanyuan-glitch/smart-doc-platform**
2. 点击绿色按钮 **<> Code**
3. 点击 **Download ZIP**
4. 解压到 `C:\smart-doc-platform`（注意：每次开始新任务前都要重新下载，确保是最新版本）

---

## 💻 第 2 步：用 VS Code 打开项目

### 安装 VS Code 和 Qwen（联系 IT）

⚠️ **VS Code 和 Qwen（通义千问）需要联系 IT 安装，不要自己下载！**

### 打开项目

1. 打开 VS Code
2. 点左上角 **File（文件）** → **Open Folder（打开文件夹）**
3. 选择 `C:\smart-doc-platform`，点 **选择文件夹**

✅ 好了！你现在可以看到所有代码了！

---

## 🤖 第 3 步：让 Qwen 帮你写代码（你只需要复制粘贴）

### 打开 Qwen

1. 打开浏览器访问：**https://qwen.ai**
2. 登录你的账号

### 告诉 Qwen 你想做什么

**例子：**
```
我想修改文档审核页面，文件路径是 frontend/src/views/Review.vue
帮我把页面标题改成"文档审核中心"
```

**你不需要自己写代码！** Qwen 会给你完整的代码。

### 把 Qwen 给的代码复制到 VS Code

1. 在 VS Code 里按 **Ctrl + P**，输入文件名（如 `Review.vue`），按回车
2. 找到 Qwen 说的位置
3. 删除旧代码，粘贴 Qwen 给的新代码
4. 按 **Ctrl + S** 保存

就这么简单！你不需要懂代码，复制粘贴就行！

---

## ⬆️ 第 4 步：上传到 GitHub（让别人看到你的修改）

### 方式 A：用 VS Code 上传（推荐）

1. 在 VS Code 左侧找到 **Source Control** 图标
2. 点文件名旁边的 **+** 号（加入暂存区）
3. 在顶部输入框写你做了什么，例如：`张三：修改文档审核页面标题`
4. 点 **✓ Commit**
5. 点 **Publish Branch**

✅ 完成！你的修改已经上传到 GitHub 了！

### 方式 B：在 GitHub 网页上传

1. 打开 **https://github.com/caoyanyuan-glitch/smart-doc-platform**
2. 找到你修改的文件，点进去
3. 点右上角 **✏️ 铅笔图标**
4. 把新代码粘贴进去
5. 底部填写 commit 信息，点 **Commit changes**

---

## 📋 每天的工作流程

```
1. 打开 GitHub，下载最新 ZIP
    ↓
2. 用 VS Code 打开
    ↓
3. 问 Qwen 要怎么改，复制它给的代码到 VS Code
    ↓
4. 保存（Ctrl + S）
    ↓
5. 上传到 GitHub
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

## 📁 常用文件路径（告诉 Qwen 用）

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

## 🤖 怎么问 Qwen（通义千问）

直接告诉它你想做什么就行！**你不需要懂代码！**

**模板：**
```
我想修改 [页面名称]
文件路径：[上面表格里的路径]
需求：[你想要什么效果]
```

**例子：**
```
我想修改文档审核页面
文件路径是 frontend/src/views/Review.vue
需求：把页面标题改成"文档审核中心"，加一个"批量上传"按钮
```

Qwen 会给你完整的代码，你只需要复制粘贴！

---

## ⚠️ 注意事项

1. **每次开始前先下载最新 ZIP**，避免改到旧版本
2. **告诉 Qwen 完整的文件路径**，它才能给你准确的代码
3. **改完记得上传到 GitHub**，不然别人看不到
4. **commit 信息要写清楚**：`张三：xxx`

---

## ❓ 常见问题

**Q1：Qwen 给的代码放哪里？**
A：按 **Ctrl + P**，输入文件名，找到文件，粘贴，按 **Ctrl + S** 保存。

**Q2：改完后浏览器没变化？**
A：按 **Ctrl + F5** 强制刷新。

**Q3：不小心改错了？**
A：按 **Ctrl + Z** 撤销，或者重新下载 ZIP。

**Q4：npm install 很慢？**
A：输入 `npm config set registry https://registry.npmmirror.com` 再重试。

---

> 💡 **记住：你不需要会写代码！Qwen 帮你写，你只管复制粘贴！**
