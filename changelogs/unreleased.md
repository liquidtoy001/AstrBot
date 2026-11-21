# Unreleased

- QQ Official: failed image uploads no longer log base64 payloads, avoiding dashboard freezes from oversized log entries. Retry attempts decrease from five to three, with one summary warning.

- Session waiters now wake their timeout task immediately when completed early, avoiding stale asyncio tasks for the remainder of the configured timeout.

- 「插件 → 管理行为 → 函数工具」现在只列出插件工具。Agent 运行时工具由配置文件的 AI 功能设置控制，MCP 工具可在「插件 → MCP」查看。
- Extensions → Handlers → Function Tools now lists plugin tools. Configure Agent runtime tools in the profile's AI capability settings and view MCP tools under Extensions → MCP Servers.

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
- 桌面端 ChatUI 去掉顶栏右上角的「选项」菜单：语言和主题本来就在左下角「设置 → 通用」里，「检查更新」「修改账户」「退出登录」也移到那里，有新版本时「设置」按钮上显示提示圆点。其他页面和手机端的顶栏菜单不变。
- Desktop ChatUI drops the **Options** menu in the upper-right corner: language and theme were already under **Settings → General** (bottom left), and **Check for updates**, **Change account** and **Log out** move there too; the **Settings** button shows a dot when an update is available. Other pages and phones keep the header menu.
- 双击 ChatUI 顶栏中间的会话标题，可以用原来的「编辑会话名称」对话框重命名当前对话。
- Double-click the conversation title in the middle of the ChatUI header to rename the current conversation with the usual **Edit Session Name** dialog.
- 桌面端 ChatUI 的会话面板和工作台改为在顶栏下方右侧弹出的卡片，顶栏图标不再随面板开关变化：工作台的标签栏和按钮移进卡片，原来的收起按钮改为 X；面板打开时对应的顶栏按钮保持高亮，再点一次关闭（原来会话按钮的高亮不显示）。工作台展开时只占满聊天区域，左侧栏、顶栏和窗口按钮仍可使用。手机端不变。没有插件提供可选视图时，工作台不显示「＋」（视图列表加载失败时仍显示，以便重试）。
- Desktop ChatUI opens the Session panel and the workbench as cards on the right below the top bar, and the top bar icons no longer change when a panel opens: the workbench tabs and buttons move into its card, and its hide button becomes an X. The button of an open panel stays highlighted and closes it when selected again (the Session button's highlight did not show before). An expanded workbench fills only the chat area, so the left sidebar, the top bar and the window buttons stay usable. Phones are unchanged. The workbench hides **+** while no plugin offers a view (it stays if the view list fails to load, so you can retry).

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

### ChatUI session panel / ChatUI 会话面板

- ChatUI 新增 **会话** 侧边面板（点击顶栏右侧的 **会话** 按钮打开，点击子代理标签也可打开；它和工作台共用右侧区域，同一时间只显示一个）：当前对话的模型、配置文件、人格、上下文分项、累计用量和缓存命中、压缩次数、改动过的文件和子代理。
- Add a **Session** side panel to ChatUI (open it with the **Session** button at the right of the top bar, or by selecting a sub-agent chip; it and the workbench share the right side, one at a time): the conversation's model, config profile, persona, context breakdown, total usage and cache hits, compaction count, changed files, and sub-agents.
- 会话面板可为当前对话设置更早的自动压缩阈值（窗口的 50%/40%/30%，不低于 8192 token 和窗口的 20% 中较大者，与其他按对话选项一起保存，随请求以 `compact_threshold` 发送），并可 **压缩会话** 立即总结较早上下文；回复进行中会被拒绝。
- The Session panel sets an earlier auto-compact threshold for the current conversation (50%/40%/30% of the window, never below the larger of 8192 tokens and 20% of the window, stored with the other per-conversation options and sent as `compact_threshold`) and can **Compact conversation** right away; it is refused while a reply runs.
- 会话面板列出本对话的子代理，显示当前动作、运行时间和累计用量，并可停止；派出子代理的回复下方为每个子代理显示小标签。工具卡片标题写出运行的命令或改动的文件，运行详情中思考块的标题分别统计命令、文件和子代理。
- The Session panel lists the conversation's sub-agents with their current activity, run time, and total usage, and can stop them; replies that started sub-agents show one chip per sub-agent. Tool cards name the command run or the file changed, and thinking block titles in the run details count commands, files, and sub-agents separately.
- 子代理以 AstrBot 星标显示，每个子代理一种颜色，标签和会话面板一致。子代理结果返回后模型的回复显示在派出它们的回复气泡中（只保留一组操作按钮，重新生成从原来那一轮开始），不再单独成为一个气泡；该回复保存时带上 `subagent_results`。
- Sub-agents are marked with the AstrBot star, one color per sub-agent, matching in the chips and the Session panel. The model's reply to returned sub-agent results is shown in the bubble of the reply that started them (one set of actions; regenerate reruns the original turn) instead of a bubble of its own; that reply is saved with `subagent_results`.
- 子代理的模型：通用子代理（以及没有指定模型的专用 Agent）改用派出它的这次请求所用的模型（如 ChatUI 为这条消息选择的模型），不再总是会话默认模型；子代理目录写明每个专用 Agent 的模型并列出可用聊天模型；用户点名的模型没有对应的专用 Agent 时，`spawn_agent` 可传入 `provider_id`，自动新建一个使用该模型的专用 Agent 并在会话所用的配置文件中勾选（同时派出多个只建一个，之后复用；只允许已启用的聊天模型）。此项改动适用于所有平台。
- Sub-agent models: a generic sub-agent (and a specialized agent without a model) now uses the model of the request that started it (such as the model chosen in ChatUI for that message) instead of always the session default; the sub-agent catalog states each specialized agent's model and lists the available chat models; when no specialized agent uses a model the user names, `spawn_agent` takes its `provider_id` and creates a specialized agent on that model, selected in the conversation's profile (one per model even when several spawn at once, reused afterwards; enabled chat models only). This applies to all platforms.
- ChatUI **设置 → 子代理**：修改当前对话所用配置文件的子代理设置；**单独建一份** 为 ChatUI 创建专用配置文件。
- ChatUI **Settings → Subagents**: edit the sub-agent settings of the conversation's config profile; **Create ChatUI profile** gives ChatUI its own profile.
- 新增接口 `GET /api/v1/chat/sessions/{session_id}/subagents`、`POST .../subagents/{agent_id}/cancel`、`POST .../compact`、`GET .../settings`、`PUT .../persona`，只允许会话本人访问。每轮的 `agent_stats` 新增 `context_breakdown` 和 `compactions`。
- Add `GET /api/v1/chat/sessions/{session_id}/subagents`, `POST .../subagents/{agent_id}/cancel`, `POST .../compact`, `GET .../settings`, and `PUT .../persona`, limited to the session's owner. Each turn's `agent_stats` gains `context_breakdown` and `compactions`.
