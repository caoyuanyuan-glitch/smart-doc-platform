# Requirements Document

## Introduction

在知识库管理下增加文件调用统计页，记录每个知识库文件被哪些业务模块读取、调用次数、耗时和调用账号。同时约定：在「管理员 / 普通用户」角色基线之上，用授权覆盖给单个普通用户开放指定页面或指定知识库文件。

本轮实现调用统计。页面授权与文件授权作为下轮范围，本文件保留方案约束。

## Glossary

- **角色基线**: 管理员拥有全部页面与全部知识库操作；普通用户拥有默认页面集合，知识库仅可浏览「写作规范」与「资源库」，文件操作仅预览
- **调用记录**: 一次业务模块读取或使用某个知识库文件的事件，含模块名、账号、开始时间、耗时毫秒
- **页面授权**: 在角色基线之外，把某个前端页面键授予指定用户
- **文件授权**: 在角色基线之外，把某个知识库文件或文件夹的预览、下载或编辑能力授予指定用户
- **页面键**: 与路由对应的稳定标识，例如 `polish.stats`、`qa.dashboard`、`knowledge.stats`

## Requirements

### Requirement 1

**User Story:** AS 管理员, I want 在知识库管理中查看每个文件的调用统计, so that 能知道文件被哪些模块使用以及使用频率

#### Acceptance Criteria

1. WHEN 管理员打开知识库管理, THE 系统 SHALL 提供名为「调用统计」的入口
2. WHEN 管理员进入调用统计页, THE 系统 SHALL 按文件列出调用次数、调用模块、累计耗时和调用账号数
3. WHEN 管理员筛选时间范围或模块, THE 系统 SHALL 按筛选条件刷新统计结果
4. WHILE 当前用户角色为普通用户, THE 系统 SHALL 只展示角色基线内的知识库入口，调用统计入口保持对管理员可见

### Requirement 2

**User Story:** AS 管理员, I want 查看单个文件的调用明细, so that 能核对每次调用的模块、账号和耗时

#### Acceptance Criteria

1. WHEN 管理员在统计页选择一个文件, THE 系统 SHALL 展示该文件的调用明细列表
2. WHEN 系统展示调用明细, THE 系统 SHALL 包含调用时间、模块名称、调用账号、耗时毫秒
3. IF 某次调用未绑定登录账号, THE 系统 SHALL 将调用账号显示为 `guest`

### Requirement 3

**User Story:** AS 平台, I want 在业务模块读取知识库文件时写入调用记录, so that 统计页有可核对的数据

#### Acceptance Criteria

1. WHEN 智能润色、智能问答或 AI 翻译读取一个知识库文件, THE 系统 SHALL 写入一条调用记录
2. WHEN 系统写入调用记录, THE 系统 SHALL 记录文件标识、模块名称、调用账号、耗时毫秒和发生时间
3. IF 写入调用记录失败, THE 系统 SHALL 继续完成原业务读取，并在服务日志中记录失败原因

### Requirement 4

**User Story:** AS 管理员, I want 给指定普通用户单独开放某个页面, so that 不必把该用户改成管理员（下轮实现）

#### Acceptance Criteria

1. WHEN 管理员在用户管理中为某用户添加页面授权, THE 系统 SHALL 保存该用户与页面键的授权关系
2. WHILE 某普通用户持有页面授权, THE 系统 SHALL 在侧栏展示对应菜单并允许进入该页面
3. WHEN 管理员撤销某用户的页面授权, THE 系统 SHALL 使该用户重新只看到角色基线内的页面

### Requirement 5

**User Story:** AS 管理员, I want 给指定普通用户单独开放某个知识库文件, so that 该用户可以预览角色基线之外的文件（下轮实现）

#### Acceptance Criteria

1. WHEN 管理员为某用户授予某个文件或文件夹, THE 系统 SHALL 保存目标、动作和用户的授权关系
2. WHILE 某普通用户持有文件预览授权, THE 系统 SHALL 在知识库树中展示该文件或其所属文件夹路径
3. WHEN 管理员授予下载或编辑动作, THE 系统 SHALL 在该用户的文件操作列显示对应按钮
