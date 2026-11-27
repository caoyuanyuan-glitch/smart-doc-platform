# QA Custom Cards Task List

Feature Name: qa-custom-cards
Updated: 2026-11-26

## 1. Backend Data Layer

- [x] 新增 `backend/app/models/qa_card.py`：`QaCard`、`QaCardFolder`、`QaCardSeedState`
- [x] `backend/app/database.py` 导入新模型，确认 `create_all` 创建三张表
- [x] `backend/app/crud/knowledge.py` 删除文件夹时清理卡片关联
- [x] 扩展 `backend/app/utils/qa_scenes.py` 内置卡片定义与 `seed_default_qa_cards`
- [x] `backend/app/main.py` 在知识库种子后调用卡片种子

## 2. Backend Scope and API

- [x] `backend/app/utils/knowledge_access.py` 新增 `resolve_qa_scope`
- [x] `backend/app/api/qa.py` 的 `_load_qa_documents` 改为只读已展开目录
- [x] `ask_general_question` 与 `suggestions/initial` 接入 `resolve_qa_scope`
- [x] 新增卡片序列化与表单校验
- [x] 新增 `GET/POST/PUT/DELETE /api/qa/cards` 与 `PUT /api/qa/cards/order`
- [x] `build_scene_inventory` 改为读取数据库卡片
- [x] `/api/qa/scenes/sources` 返回卡片 id、描述、颜色、隐藏状态

## 3. Frontend

- [x] `frontend/src/api/index.js` 新增卡片 CRUD 与排序方法
- [x] 新增 `frontend/src/components/QaCardManager.vue`
- [x] `frontend/src/views/QA.vue` 改为接口驱动卡片、按权限计算范围与资料数
- [x] 管理员首页增加「管理卡片」入口与空态
- [x] `frontend/src/views/QADashboard.vue` 适配数据库卡片字段

## 4. Tests and Verification

- [x] 新增 `backend/tests/test_qa_cards.py`
- [x] 改造 `backend/tests/test_qa_scenes.py`
- [x] 新增普通用户范围隔离测试
- [x] 运行相关 pytest
- [x] 重启后端，使用 Vite 编译校验前端
- [ ] 管理员与普通用户手工验收首页、管理弹窗、统计面板
