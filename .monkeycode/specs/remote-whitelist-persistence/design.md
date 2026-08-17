# 远程白名单持久化

Feature Name: remote-whitelist-persistence
Updated: 2026-08-17

## Description

白名单文件路径通过环境变量配置。开发环境使用仓库内默认文件；专用服务器使用服务器持久化目录。白名单 API 和拼写检查模块通过同一个路径读取、写入和重载数据。

## Architecture

```mermaid
flowchart LR
    A["平台用户"] --> B["白名单 API"]
    B --> C["WHITELIST_DATA_FILE"]
    C --> D["服务器持久化文件"]
    B --> E["拼写检查运行时词典"]
    D --> E
```

## Components and Interfaces

- `app.paths.get_whitelist_file`: 从 `WHITELIST_DATA_FILE` 解析白名单文件路径。
- `app.paths.WHITELIST_FILE`: 为当前后端进程提供统一的数据文件路径。
- `app.api.whitelist`: 将白名单写入配置路径，并刷新拼写检查词典。
- `app.utils.spell_checker`: 服务导入和刷新时从配置路径加载白名单。

## Data Models

数据结构沿用 `whitelist.json` 的分类数组和词条字段，服务器路径变化不改变词条格式。

## Correctness Properties

- 一个后端进程中的白名单 API 与拼写检查模块使用相同文件路径。
- 服务器配置路径中的新增词条可在同一进程即时生效。
- 服务器重启后的白名单词典从配置路径重建。
- 本地开发环境与服务器环境的文件路径由各自环境变量隔离。

## Error Handling

- 白名单服务创建配置文件父目录。
- 文件格式读取异常时，白名单服务使用默认词条集合继续提供接口。
- 文件写入异常由 API 请求返回错误状态，避免将未保存词条显示为成功。

## Test Strategy

- 验证 `WHITELIST_DATA_FILE` 覆盖默认路径。
- 验证变量为空时使用后端应用目录内的默认路径。
- 运行白名单与拼写检查回归测试。
