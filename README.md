# 指令转LLM插件

这个插件允许你将各种指令转换为LLM函数调用，让AI能够在对话中主动执行指令并获取响应。拆分自隔壁插件[ai-reminder](https://github.com/kjqwer/astrbot_plugin_sy)独立出来作为一个功能。

## 功能特性

- 🔄 将指令映射为LLM函数调用
- 📝 支持动态添加和管理指令映射
- 🎯 支持指令参数传递
- 💾 使用 AstrBot 官方配置系统持久化（支持 WebUI）
- 🛠️ 提供完整的命令行管理工具
- 🧩 映射模块化管理：启停、分组、批量编辑
- 🔄 兼容旧版 JSON 映射并自动迁移

## 快速开始

### 1. 添加指令映射

首先，你需要将现有的指令映射为LLM函数：

```
<唤醒前缀>cmd2llm add rmd--ls list_reminders 列出所有提醒
```

![添加指令映射](https://sywb.top/Staticfiles/pic/command1.png)

### 2. AI调用指令

映射完成后，AI就可以通过LLM函数调用这些指令：

![AI调用指令](https://sywb.top/Staticfiles/pic/command2.png)

## 使用方法

### 命令行操作

#### 添加指令映射
```
<唤醒前缀>cmd2llm add <指令名> <LLM函数名> [描述]
```

指令名格式：
- 单个指令：`rmd`
- 多级指令：`rmd--ls`, `rmd--add`, `rmd--help`
- 支持任意数量的 `--` 连接

示例：
```
<唤醒前缀>cmd2llm add rmd--ls list_reminders 列出所有提醒
<唤醒前缀>cmd2llm add rmd--help show_help 显示提醒帮助
<唤醒前缀>cmd2llm add weather get_weather 获取天气信息
```

#### 列出所有映射
```
<唤醒前缀>cmd2llm ls [--enabled|--disabled|--all]
```

示例：
```
<唤醒前缀>cmd2llm ls --enabled
<唤醒前缀>cmd2llm ls --disabled
```

输出示例：
```
当前配置的指令映射：
1. rmd ls -> list_reminders (列出所有提醒)
2. rmd help -> show_help (显示提醒帮助) [已禁用]
3. weather -> get_weather (获取天气信息)
```

按状态过滤示例：
```
当前已启用的指令映射：
1. rmd ls -> list_reminders (列出所有提醒)
2. weather -> get_weather (获取天气信息)
```

#### 删除映射
```
<唤醒前缀>cmd2llm rm <指令名>
```

注意：删除时需要使用完整的指令名，例如：
- 删除 `rmd--ls` 映射：`<唤醒前缀>cmd2llm rm rmd--ls`
- 删除 `weather` 映射：`<唤醒前缀>cmd2llm rm weather`

#### 启用映射
```
<唤醒前缀>cmd2llm enable <指令名>
```

示例：
```
<唤醒前缀>cmd2llm enable rmd--ls
```

#### 禁用映射
```
<唤醒前缀>cmd2llm disable <指令名>
```

示例：
```
<唤醒前缀>cmd2llm disable rmd--ls
```

#### 执行指令
```
<唤醒前缀>cmd2llm exec <指令名> [参数]
```

示例：
```
<唤醒前缀>cmd2llm exec rmd--ls
```

参数说明（与代码行为一致）：
- `args` 会按原样透传给目标指令，不会在插件内部强制解析。
- 因此可使用无参数、`key=value`、以及包含空格/分隔符（如 `|`）的长文本参数。

#### 显示帮助
```
<唤醒前缀>cmd2llm help
```

### 动态LLM函数

插件会自动为每个指令映射注册对应的LLM函数：

- 映射 `rmd ls` → `list_reminders` 会注册 `list_reminders` 函数
- 映射 `rmd help` → `show_help` 会注册 `show_help` 函数
- 映射 `weather` → `get_weather` 会注册 `get_weather` 函数

这些动态函数会被系统识别，AI可以直接调用它们。

## 配置说明（推荐 WebUI）

插件已支持 AstrBot 官方 `_conf_schema.json`，可直接在 WebUI 插件配置页完成全部管理。

### 1) 基础行为（basic_config）
- `enable_plugin`：插件总开关
- `auto_refresh_on_change`：命令增删映射后自动刷新动态函数
- `strict_validation`：严格校验 LLM 函数名（仅字母/数字/下划线）

### 2) 模块化映射（mapping_config）
- `command_mappings`：可视化增删改映射项
  - `enabled`：是否启用该映射
  - `command_name`：指令名（例如 `rmd ls`）
  - `llm_function`：函数名（例如 `list_reminders`）
  - `description`：给 AI 的用途描述
  - `arg_description`：该映射专属参数说明（告诉 AI args 应如何填写）
  - `group`：分组标签
  - `aliases`：预留别名字段（后续扩展）
- `allow_duplicate_llm_function`：是否允许多个指令复用同一函数名

### 3) 执行行为（execution_config）
- `capture_timeout_sec`：捕获被触发指令响应的超时秒数
- `forward_interval_sec`：多条消息转发间隔
- `response_mode`：
  - `forward_only`（默认，推荐）：只在会话中转发，尽量避免触发额外 LLM 复述
  - `forward_and_text`：平台转发 + 返回文本（可能导致 LLM 再加工回复）
  - `text_only`：只返回文本
 
> 如果你的目标是“只执行，不要 AI 再说一遍”，请保持 `forward_only`。

### 6) 前缀行为（与主框架一致）
- 管理命令（`cmd2llm ...`）遵循 AstrBot 主框架的 `wake_prefix`。
- 执行映射时，插件会自动读取当前会话 `wake_prefix` 并拼接到目标指令。
- 如果传入的指令本身已带前缀，插件不会重复拼接前缀。

### 4) 工具参数说明（tool_config）
- `tool_description`：全局工具描述（统一告诉 LLM 这个插件在做什么）
- `arg_description`：全局 args 参数说明（默认模板）

说明：
- 如果某个映射填写了 `mapping_config.command_mappings[].arg_description`，则优先使用该说明。
- 否则回退到 `tool_config.arg_description`。

### 5) 兼容迁移（compat_config）
- `auto_migrate_legacy_json`：自动迁移旧版 JSON 数据
- `keep_legacy_backup`：保留旧文件备份（`.json.bak`）
- `migration_once_flag`：迁移完成标记

> 旧版 `data/plugin_data/command_to_llm/command_mappings.json` 会在首次升级时自动迁移到官方 config。

## 注意事项

1. **指令映射是全局的**，所有会话共享
2. **指令名称区分大小写**
3. **确保映射的LLM函数确实存在**，否则执行时会失败
4. **建议为每个映射添加清晰的描述**，帮助AI理解指令用途
5. **删除映射时使用完整的指令名**，包括 `--` 分隔符
6. **插件会自动处理多平台适配**，支持各种消息平台

## 常见问题

删除时需要使用完整的指令名。例如，如果映射是 `rmd--ls`，删除时也要用 `rmd--ls`，不能用 `rmd ls` 或 `rmd`。

命令中的 `<唤醒前缀>` 请替换为你在 AstrBot 主框架配置的前缀（例如 `/`、`~`）。


## 作者

- 作者：kjqwdw
- 版本：v1.1.0

## 支持

如需帮助，请参考 [AstrBot插件开发文档](https://astrbot.soulter.top/center/docs/%E5%BC%80%E5%8F%91/%E6%8F%92%E4%BB%B6%E5%BC%80%E5%8F%91/)

## 问题反馈

如有问题或建议，请访问以下地址反馈：
[反馈](https://github.com/kjqwer/astrbot_plugin_command_to_llm/issues)
