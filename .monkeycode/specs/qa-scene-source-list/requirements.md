# Requirements Document

## Introduction

管理员在智能问答「统计面板」（原问答看板）中查看知识库问答每个板块实际检索范围内的文件，并可以跳转到知识库预览该文件。

## Glossary

- **板块**: 知识库问答首页的场景卡片，当前包括查写作规范与风格、找表达句式、内容审核与自检、查术语、中英互译、找文件资料
- **统计面板**: 智能问答菜单中的统计页，路由为 `/qa/dashboard`，原名称「问答看板」
- **资料清单**: 统计面板中仅管理员可见的区块，列出某板块对应知识目录及其子目录中、问答检索会纳入的知识库文件
- **管理员**: 角色为 `admin` 的登录用户
- **普通用户**: 角色为 `user` 的登录用户

## Requirements

### Requirement 1

**User Story:** AS 管理员, I want 查看知识库问答每个板块对应的资料清单, so that 能确认问答检索实际覆盖了哪些文件

#### Acceptance Criteria

1. WHEN 管理员打开智能问答菜单, THE 系统 SHALL 展示名为「统计面板」的菜单项
2. WHEN 管理员打开统计面板, THE 系统 SHALL 一次列出全部板块及其资料
3. WHEN 管理员查看某板块的资料清单, THE 系统 SHALL 列出该板块映射目录及其子目录中的知识库文件
4. WHEN 管理员查看资料清单, THE 系统 SHALL 展示每份资料的文件名、所属目录路径、文件类型和更新时间
5. WHEN 管理员查看资料清单, THE 系统 SHALL 同时展示该板块的目录数量和资料份数
6. IF 某板块映射目录不存在或目录下没有文件, THE 系统 SHALL 展示该板块暂无资料的说明
7. WHEN 管理员点击清单中的某份资料, THE 系统 SHALL 跳转到知识库并预览该文件

### Requirement 2

**User Story:** AS 管理员, I want 资料清单与问答检索范围一致, so that 清单反映用户提问时真正会搜到的文件

#### Acceptance Criteria

1. WHEN 系统生成某板块的资料清单, THE 系统 SHALL 使用与该板块场景卡片相同的知识目录路径映射
2. WHEN 系统收集资料清单, THE 系统 SHALL 包含映射目录子孙目录中的文件
3. WHEN 系统收集资料清单, THE 系统 SHALL 跳过「AI agent知识库」及其子孙目录中的文件

### Requirement 3

**User Story:** AS 普通用户, I want 继续按板块提问, so that 使用问答时不会看到管理用的资料明细

#### Acceptance Criteria

1. WHEN 普通用户打开知识库问答页, THE 系统 SHALL 仅展示板块名称、说明和资料份数
2. WHEN 普通用户打开智能问答菜单, THE 系统 SHALL 展示问答、历史和统计面板入口
3. WHEN 普通用户请求资料清单接口, THE 系统 SHALL 返回 403
4. WHEN 普通用户打开统计面板, THE 系统 SHALL 隐藏资料清单区块

### Requirement 4

**User Story:** AS 管理员, I want 资料清单随知识库变化自动更新, so that 不需要手动刷新就能看到最新目录和文件

#### Acceptance Criteria

1. WHEN 管理员展开资料清单, THE 系统 SHALL 立即从知识库读取最新目录和文件
2. WHILE 资料清单处于展开状态且页面可见, THE 系统 SHALL 每 10 秒自动刷新一次
3. WHEN 管理员切回统计面板或浏览器窗口重新获得焦点, THE 系统 SHALL 在页面可见且资料清单展开时立即刷新
4. WHEN 知识库中的文件新增、删除、移动或重命名, THE 系统 SHALL 在下一次刷新时反映最新结果
5. IF 自动刷新失败且已有清单数据, THE 系统 SHALL 保留上一次成功数据
