# Unreleased

- QQ Official: failed image uploads no longer log base64 payloads, avoiding dashboard freezes from oversized log entries. Retry attempts decrease from five to three, with one summary warning.

### ChatUI history / ChatUI 历史记录

- 一轮回复只保存为一条历史记录：流式分段、工具调用和按钮卡片都更新同一条记录，刷新后不再拆成多个气泡（SSE 与 WebSocket 相同）。已拆开的旧记录不会合并。
- Each assistant turn is saved as one history record. Streamed segments, tool calls and button cards update the same record, so a reply no longer splits into several bubbles after a reload (SSE and WebSocket alike). Records split before this change are not merged.
- 工具调用在开始时就占好位置，结果到达后原地更新：中途保存不再把调用拆成两半，耗时正确，后面的按钮卡片也不会排到调用前面。
- A tool call takes its place when it starts and is completed in place when its result arrives, so mid-turn saves no longer split it, its duration is correct, and a later button card stays after it.
- 回复结束时仍未返回的工具调用标为「已中断，结果未知」（实时和刷新后一致），不再一直计时。
- A tool call still without a result when the reply ends is marked **Interrupted, result unknown**, live and after a reload, instead of showing a running timer.
- 同一轮里两段模型消息之间没有工具调用时，补一个段落分隔，避免文字连在一起；只作用于 WebChat，其他平台的输出不变。
- When two model messages in one turn follow each other without a tool call in between, WebChat inserts a paragraph break so the text does not run together. Other platforms are unchanged.
- 按钮回调的注册改为在后台线程写入数据库，不再阻塞事件循环（所有平台共用）；过期一天以上的回调从缓存和数据库中清理。
- Button callback registration writes to the database on a background thread instead of blocking the event loop (shared by all platforms). Callbacks expired for over a day are removed from the cache and the database.
- 分块上传的清理任务在没有事件循环时不再留下未等待的协程。
- The chunked-upload cleanup task no longer leaves an unawaited coroutine when no event loop is running.

### Overview page / 总览页

- 欢迎 → 总览：保留 `/welcome` 地址，显示每日用量对比、系统状态和机器人错误详情。
- Welcome → Overview: Keep `/welcome` accessible and show daily usage comparisons, system status, and bot error details.
- 总览统计并入 `/api/v1/stats`，新增 `daily_usage` 与 `system`，移除开发阶段的 `/api/v1/stats/overview`。使用 `sections` 选择 `messages`、`daily_usage`、`process`、`system` 或 `instances`；省略时返回全部数据。旧接口 `/api/stat/get` 同样支持。
- Consolidate overview metrics into `/api/v1/stats`, adding `daily_usage` and `system` and removing the development-only `/api/v1/stats/overview`. Use `sections` to select `messages`, `daily_usage`, `process`, `system`, or `instances`; omit it for the full response. Legacy `/api/stat/get` also supports this parameter.

### ChatUI file changes and undo / ChatUI 文件改动与撤销

- 本地运行环境下，写入和编辑文件工具的卡片显示改动预览（路径、增删行数、改动的那一段），并可撤销这一次改动；只有对话所属的用户、且文件仍是改动刚完成时的状态才能撤销，符号链接和被替换的文件会被拒绝，恢复采用原子替换。新增接口 `POST /api/v1/chat/file-changes/{change_id}/undo`（拒绝时返回 409）。删除对话或分支追问时清除其撤销记录。
- In the local computer runtime, file write and edit tool cards show a preview of the change (path, lines added and removed, the changed region) and can undo that change. Only the owner of the conversation can undo, and only while the file is unchanged since; symbolic links and replaced files are refused, and the file is restored with an atomic replace. Adds `POST /api/v1/chat/file-changes/{change_id}/undo` (409 when refused). Deleting a conversation or thread removes its undo records.

### Plugin AI documentation / 插件 AI 文档

- 调用 AI → AI：按模型、Agent、工具、会话与对话、其他拆分文档。多 Agent 编排归入构建自定义 Agent 的示例，人格管理归入其他；原 AI 地址保留为概览入口。
- Call AI → AI: Split the guide into Models, Agents, Tools, Sessions and Conversations, and Other APIs. Place multi-agent orchestration under custom Agent construction and persona management under Other APIs. Keep the original AI URL as an overview.

### ChatUI polish / ChatUI 小改进

- ChatUI 报错卡片新增四种：API 密钥被拒、找不到模型、模型需要改用 OpenAI Responses 提供商类型才能调用工具（三者都带「配置模型」按钮），以及频率限制或额度用尽。依赖模型请求失败时的稳定错误代码。
- ChatUI error cards add four cases: a rejected API key, a model that is not found, a model that needs the OpenAI Responses provider type for tool calls (each with a **Configure models** button), and a rate limit or quota. They rely on the stable error codes of failed model requests.
- 模型选择器新增按对话的快速模式开关（输出更快、价格更高）：官方 OpenAI、xAI、OpenRouter 接口发送 `service_tier: "priority"`，官方 Anthropic 接口上的 Claude Opus 5.5、Fable 5.2、Mythos 5.2 发送 `speed: "fast"`。是否支持由后端判断，提供商列表中支持的条目带 `supports_fast_mode: true`；聊天请求新增 `fast_mode`，`ProviderRequest.fast_mode` 可供插件读写。
- Add a per-conversation fast mode switch to the model selector (faster output at a higher price): `service_tier: "priority"` on the official OpenAI, xAI and OpenRouter APIs, and `speed: "fast"` for Claude Opus 5.5, Fable 5.2 and Mythos 5.2 on the official Anthropic API. The backend decides support; supported entries in the provider list carry `supports_fast_mode: true`. Chat requests accept `fast_mode`, and `ProviderRequest.fast_mode` is available to plugins.
- ChatUI 的模型按钮只显示模型名，不再带提供商前缀；悬停显示完整的提供商 ID。
- The ChatUI model button shows only the model name, without the provider prefix; hover to see the full provider ID.
- 自己发送的消息也有复制按钮；消息下方的按钮悬停时显示名称和说明。
- Your own messages get a copy button, and the buttons under a message show a name and description on hover.
- 回复进行中时，头像中的 AstrBot 标志播放动画（小星环绕、金蓝交替）；静止时仍是原来的标志，系统开启减少动态效果时不播放。
- While a reply is in progress the AstrBot mark in its avatar is animated (the small star orbits while gold and blue take turns); at rest it is the plain mark, and it stays still when the system asks for reduced motion.

### Tool approval and permission modes / 工具审批与权限档位

- 新增「需要审批的工具」（`agent.config.misc.tool_approval.tools`）和审批超时：名单内的工具执行前需要发起人批准。ChatUI 在输入框上方显示审批卡片，结果收进这轮回复的运行详情；其他平台发送确认码，支持按钮的平台附带按钮。只有发起人的回复有效，后台唤醒不会被当作答复。
- Add **Tools requiring approval** (`agent.config.misc.tool_approval.tools`) and an approval timeout. Listed tools wait for the requester's approval: ChatUI shows an approval card above the input box and keeps the outcome in the reply's run details; other platforms get a reply code, plus buttons where supported. Only the requester's reply counts, and background wakeups never answer an approval.
- 批准创建或修改定时任务（`future_task`）时，同时批准任务到点运行时用到的名单内工具；未经批准的任务向创建者请求批准。
- Approving the creation or edit of a scheduled task (`future_task`) also approves the listed tools it uses on schedule. Tasks created without approval ask their creator.
- ChatUI 新增按对话的权限档位（工作区 / 请求批准 / 完全访问），位于输入框加号旁边。档位只会收窄角色的本地权限策略；「完全访问」不会传给定时任务。审批卡片上的「本对话不再询问」不会放宽访问：在「请求批准」下切到「完全访问」，在「工作区」下保持工作区并显示「工作区 · 不再询问」。新增 `permission_mode` 请求字段（含 `workspace_no_ask`）和 `PUT /api/v1/chat/sessions/{session_id}/permission-mode`（只能修改自己的 WebChat 会话）。
- Add per-conversation permission modes in ChatUI (Workspace / Ask for approval / Full access) next to **+** in the input box. Modes only narrow the role's local permission policy, and Full access never passes to scheduled tasks. **Don't ask again in this conversation** on an approval card never widens access: from Ask for approval it switches to Full access, and from Workspace it stays in the workspace, shown as **Workspace · not asking**. Chat requests accept `permission_mode` (including `workspace_no_ask`), and `PUT /api/v1/chat/sessions/{session_id}/permission-mode` changes it for the caller's own WebChat sessions.
- ChatUI 的按对话选项存放在该对话的 ChatUI 偏好记录里，随发送、重新生成、分支追问和 WebSocket 请求一起发送，删除对话时清除；后端用 `resolve_webchat_chat_options()` 校验并放到事件上，非法值会被忽略。
- ChatUI per-conversation options are stored in the conversation's ChatUI preferences, sent with messages, regenerations, thread messages and WebSocket requests, and cleared when the conversation is deleted. The backend validates them with `resolve_webchat_chat_options()` and puts them on the event; invalid values are ignored.
- `ActionRow` 新增可选字段 `single_use`、`title`、`detail`、`tool_call_id`，目前只有 WebChat 使用。
- `ActionRow` gains optional `single_use`, `title`, `detail`, and `tool_call_id` fields, used by WebChat only for now.

### Plugin view documentation / 插件视图文档

- 插件可视化视图、ChatUI 交互卡片 → 可折叠的「插件可视化视图」章节，按独立插件页面、消息交互组件、工作台页面组织教程；共享 Bridge API 和后端 Web API 单独列出。旧文档链接及章节锚点跳转到对应新页面。
- Plugin Views and ChatUI Cards → one collapsible Plugin Views section with standalone page, message component, and workbench tutorials, plus shared Bridge and backend Web API references. Previous document URLs and section anchors redirect to their new locations.

- 三类视图教程分别提供 Meme Manager 独立页面、阅读清单消息演示、上下文用量常驻工作台示例，并附实机截图及示例插件。
- Add target-specific examples: Meme Manager for standalone pages, an interactive reading list for messages, and a resident context-usage workbench, with screenshots and example plugins.

### Plugin view registration / 插件视图注册

- `Star.chatui_views` → `metadata.yaml` 的 `views`：默认标题和描述随声明保存，i18n 的 `views.<name>`（兼容 `pages.<name>`）按字段覆盖；没有翻译时回退到 metadata。旧的独立页面声明省略 target 时仍为 `plugin_page`。
- Move view declarations from `Star.chatui_views` to `metadata.yaml` under `views`. Keep default labels in metadata and override them with i18n `views.<name>` (legacy `pages.<name>` remains supported). Existing declarations without a target remain standalone `plugin_page` views.
- `chat_workbench` + `launcher=True` → `chat_workbench_with_launcher`：同一视图既能由消息或工具打开，也能从工作台「＋」打开。只由插件打开的视图继续使用 `chat_workbench`。
- Replace `chat_workbench` + `launcher=True` with `chat_workbench_with_launcher` for views that can open from messages/tools and from **+**. Keep `chat_workbench` for plugin-opened views without a launcher entry.
### ChatUI thinking level / ChatUI 思考程度

- 模型选择器顶部新增按对话的思考程度（低 / 中 / 高），随发送、重新生成、WebSocket 和分支追问一起发送，按提供商类型映射到 OpenAI `reasoning_effort`、Responses `reasoning.effort`、Anthropic 自适应思考或思考预算、Gemini 思考等级或预算；只作用于主提供商，不改动提供商配置。新增 `ProviderRequest.reasoning_effort`，插件可读取或修改。
- Add a per-conversation thinking level (low / medium / high) at the top of the ChatUI model selector. It is sent with messages, regenerations, WebSocket requests, and thread messages, and is mapped per provider type to OpenAI `reasoning_effort`, Responses `reasoning.effort`, Anthropic adaptive thinking or a thinking budget, and a Gemini thinking level or budget. It applies to the primary provider only and leaves provider configuration unchanged. `ProviderRequest.reasoning_effort` is new and available to plugins.
- 聊天请求新增按对话选项 `reasoning_effort`（`POST /api/v1/chat`、重新生成、分支追问消息及 WebSocket `send`），非法值会被忽略。
- Chat requests accept the per-conversation option `reasoning_effort` (`POST /api/v1/chat`, regenerate, thread messages, and WebSocket `send`); invalid values are ignored.
