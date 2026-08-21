# Requirements Document

## Introduction

平台部署到专用服务器后，白名单词条需要保存到服务器持久化目录，并在服务重启后继续参与拼写检查。本地开发环境保留独立的数据文件。

## Glossary

- **白名单数据文件**: 保存平台用户新增白名单词条的 JSON 文件。
- **本地开发环境**: 开发人员在工作区启动的后端服务。
- **服务器环境**: 专用服务器上对外提供服务的后端实例。
- **持久化目录**: 服务器发布更新和服务重启后继续保留数据的目录。

## Requirements

### Requirement 1: 环境隔离的白名单存储

**User Story:** AS 平台管理员, I want 为服务器配置独立的白名单数据文件, so that 平台用户新增的词条保留在服务器环境中。

#### Acceptance Criteria

1. WHEN 后端进程读取 `WHITELIST_DATA_FILE`, 系统 SHALL 使用该变量指定的白名单数据文件。
2. WHEN `WHITELIST_DATA_FILE` 为空, 系统 SHALL 使用后端应用目录中的默认白名单数据文件。
3. WHEN 平台用户新增、导入、编辑或删除白名单词条, 系统 SHALL 写入当前后端进程配置的数据文件。
4. WHEN 服务器后端进程重启, 系统 SHALL 从已配置的数据文件加载白名单词条。

### Requirement 2: 服务器部署配置

**User Story:** AS 部署管理员, I want 配置服务器持久化目录, so that 代码发布过程保留白名单运行数据。

#### Acceptance Criteria

1. WHEN 部署管理员配置服务器环境变量, 系统 SHALL 支持 `/var/lib/smart-doc-platform/whitelist.json` 作为白名单数据文件路径。
2. WHEN 服务器目录缺失, 白名单服务 SHALL 创建数据文件的父目录。
3. WHEN 白名单数据文件写入成功, 拼写检查服务 SHALL 刷新运行时白名单。
