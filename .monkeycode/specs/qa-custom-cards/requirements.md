# Requirements Document

## Introduction

管理员在智能问答模块创建、编辑和管理知识库问答卡片，并为卡片勾选知识库文件夹作为检索范围。新卡片保存后自动出现在知识库问答首页，普通用户可直接使用。统计面板的资料清单与问答卡片共用同一数据源。

## Glossary

- **卡片**: 知识库问答首页的场景入口，定义一组知识库文件夹作为检索范围
- **检索范围**: 卡片关联的文件夹及其子孙目录中的知识库文件
- **内置卡片**: 系统初始化时创建的四张默认卡片
- **管理员**: 角色为 `admin` 的登录用户
- **普通用户**: 角色为 `user` 的登录用户
- **资料清单**: 统计面板中展示卡片覆盖目录和文件的区块

## Decisions

- 管理能力：管理员可新建、编辑、删除、排序和隐藏卡片
- 普通用户权限：卡片对普通用户可见，检索范围收窄为卡片范围与用户可读文件夹的交集；交集为空时保留卡片并标记暂无可用资料
- 卡片字段：标题、说明、分类标签、主题色、推荐问题、文件夹集合、首页显示状态和排序

## Requirements

### Requirement 1

**User Story:** AS 管理员, I want 在智能问答模块管理问答卡片, so that 能根据业务变化调整知识库检索入口

#### Acceptance Criteria

1. WHEN 管理员打开知识库问答首页, THE 系统 SHALL 展示「管理卡片」入口
2. WHEN 管理员提交有效卡片表单, THE 系统 SHALL 创建卡片并保存卡片字段与文件夹范围
3. WHEN 管理员修改已有卡片, THE 系统 SHALL 保存修改后的卡片字段与文件夹范围
4. WHEN 管理员删除卡片, THE 系统 SHALL 从首页和统计面板移除该卡片
5. WHEN 管理员调整卡片顺序或首页显示状态, THE 系统 SHALL 按调整后的结果展示卡片
6. IF 卡片标题为空或未选择任何文件夹, THEN THE 系统 SHALL 拒绝保存并提示原因
7. WHEN 普通用户请求卡片管理接口, THE 系统 SHALL 返回 403

### Requirement 2

**User Story:** AS 管理员, I want 为卡片勾选知识库文件夹, so that 卡片只检索指定范围

#### Acceptance Criteria

1. THE 系统 SHALL 允许管理员为一组卡片字段配置标题、说明、分类标签、主题色、推荐问题、文件夹集合、首页显示状态和排序
2. THE 系统 SHALL 支持从知识库目录树中多选文件夹
3. THE 系统 SHALL 将所选文件夹及其子孙目录纳入卡片检索范围
4. WHEN 同一文件夹被重复选择, THE 系统 SHALL 在同一卡片中只计算一次
5. WHEN 文件夹在知识库中被移动或重命名, THE 系统 SHALL 保持卡片与文件夹的关联

### Requirement 3

**User Story:** AS 普通用户, I want 使用管理员创建的卡片提问, so that 能快速检索业务需要的知识范围

#### Acceptance Criteria

1. WHEN 新卡片保存成功, THE 系统 SHALL 在知识库问答首页展示该卡片
2. WHEN 普通用户进入卡片并提问, THE 系统 SHALL 只在卡片关联文件夹及其子孙目录中检索
3. WHEN 卡片关联目录没有可用文件, THE 系统 SHALL 展示暂无资料的提示
4. WHEN 管理员将卡片设置为不在首页显示, THE 系统 SHALL 在首页隐藏该卡片并保留在统计面板
5. WHEN 管理员调整卡片顺序, THE 系统 SHALL 按顺序展示卡片
6. WHEN 卡片关联的文件夹被删除, THE 系统 SHALL 保留卡片并更新其可用资料范围

### Requirement 4

**User Story:** AS 普通用户, I want 只检索自己有权访问的资料, so that 知识库权限在问答中继续生效

#### Acceptance Criteria

1. WHEN 普通用户使用卡片提问, THE 系统 SHALL 只在卡片范围和用户可读文件夹的交集中检索
2. WHEN 普通用户查看卡片资料数量, THE 系统 SHALL 只统计用户可读文件夹中的文件
3. IF 卡片关联的文件夹对当前用户均不可读, THEN THE 系统 SHALL 展示卡片并标记暂无可用资料
4. WHEN 普通用户请求卡片管理接口, THE 系统 SHALL 返回 403

### Requirement 5

**User Story:** AS 管理员, I want 统计面板与卡片配置保持一致, so that 能确认每个卡片实际覆盖的资料

#### Acceptance Criteria

1. WHEN 系统生成统计面板资料清单, THE 系统 SHALL 使用与知识库问答首页相同的卡片和文件夹配置
2. WHEN 卡片新增、编辑或删除, THE 系统 SHALL 在下一次自动刷新时更新资料清单
3. WHEN 管理员查看资料清单, THE 系统 SHALL 展示每张卡片的目录数量和资料份数
4. WHEN 管理员点击资料清单中的文件, THE 系统 SHALL 跳转到知识库并预览该文件

### Requirement 6

**User Story:** AS 系统管理员, I want 系统保留现有问答卡片, so that 升级后现有使用方式不受影响

#### Acceptance Criteria

1. WHEN 系统首次初始化卡片数据, THE 系统 SHALL 将现有四张卡片写入数据库
2. THE 系统 SHALL 保留现有卡片的标识、标题、说明、分类标签、主题色、推荐问题和目录范围
3. THE 系统 SHALL 允许管理员编辑、排序、隐藏或删除内置卡片
