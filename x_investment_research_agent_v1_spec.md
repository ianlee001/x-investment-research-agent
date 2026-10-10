# X Investment Research Agent — V1 实施规格（修订版）

修订日期：2026-10-08。本文区分官方能力、项目决策和已验证结果，不将架构选择描述为官方要求。原稿保存在 [docs/spec_v1_original.md](docs/spec_v1_original.md)；实际验收记录见 [docs/validation.md](docs/validation.md)。

## 1. 产品边界

面向个人的投资研究工作台：跟踪公开 X 账号、保留近期可访问帖子、提取与核查投资断言，结合公开披露、网页和行情生成带来源的研究报告；提供关注列表、研究对话、人工审批、长期偏好和定时简报。

V1 实现 Phase 1–5。不存在自动交易、收益预测保证、自动买卖建议执行、RAG、向量数据库、Embedding、OSS、MinerU、PDF 上传或多 Agent。采用单用户本地部署。第三方服务权限、套餐、内容授权和语义判断不能通过“拥有 API Key”推定已满足。

## 2. 技术组合与理由

| 组件 | V1 用途 | 使用边界 |
|---|---|---|
| Python / FastAPI | 业务 API、SSE、静态前端服务 | API 进程不拥有研究执行生命周期 |
| React / TypeScript / Vite | 七个研究页面、审批及流式对话 | 所有业务内容来自实际 API；不填充模拟行情 |
| PostgreSQL / SQLAlchemy / Alembic | 业务数据、任务、事件、迁移、缓存和共享限速 | 不使用 SQLite 替代持久审批验证 |
| LangChain `create_agent` | 单 Agent 工具循环 | 内部由 LangGraph 执行；不另建重复编排图 |
| LangGraph Postgres Saver / Store | 会话检查点、跨会话键值记忆 | Store 按 namespace/key 读取，不启用语义检索 |
| Runtime / Middleware | 注入运行身份，预算、日志、工具错误及 HITL | Runtime 由框架注入，不作为模型可填写的工具参数 |
| FastMCP / `langchain.mcp.MCPAdapter` | 本地数据工具与远程 Tavily MCP | 锁定版本、管理连接上下文、限定工具名单 |
| APScheduler 3 | 定时入队 X 同步、简报、帖子复核 | 唯一 Worker 注册持久任务，固定 ID、合并错过执行 |
| DashScope OpenAI 兼容接口 | Qwen 工具调用、结构化输出和对话 | 使用实测模型/端点；不假设任意模型均支持相同能力 |

LangChain 官方说明 `create_agent` 基于 LangGraph，并提供 Runtime、Middleware、工具及结构化输出能力。`langchain.mcp` 当前带 beta 标识，因此本项目采用锁文件和协议集成测试控制升级风险。[Agent](https://docs.langchain.com/oss/python/langchain/agents)、[Runtime](https://docs.langchain.com/oss/python/langchain/runtime)、[MCP](https://docs.langchain.com/oss/python/langchain/mcp)。

项目锁定 LangChain 1.4.3；精确传递依赖以 `uv.lock` 和 `frontend/package-lock.json` 为准。选用这些组件是工程决策，并不意味着更小项目必须使用全部组件。

## 3. 数据源契约

### X

- 使用官方 API 的用户查询、用户时间线、按 ID 查询帖子；近期搜索默认关闭，需显式配置且具备权限。
- Snowflake ID 始终是字符串；优先完整 `note_tweet.text`，保存 cashtag 数组、引用关系和编辑历史 ID。
- 初次历史回填有界，默认 3 页、每页 20 条，明确不等于全历史。
- 增量同步保留固定 `since_id` 下界与分页 token，完成全部分页后才推进水位。中断保存游标，分页失效从原下界重试。部分错误不能当作完整成功。
- 近期搜索与全历史搜索是不同能力；不以搜索接口代替完整用户历史。[用户帖子接口](https://docs.x.com/x-api/users/get-posts)、[搜索能力](https://docs.x.com/x-api/posts/search/introduction)。
- 每 6 小时安排保留帖子的可见性复核；超过 24 小时未成功复核的帖子不再展示。已不可访问的帖子撤去正文及引用内容，并保守撤回相关报告/对话、来源片段、事件与检查点；关联写入的已保存观点按操作记录清理。应用停止时无法继续远程复核，重新启动时将复核入队。此机制不能替代开发者遵守平台内容处理要求。[X 开发者指南](https://docs.x.com/developer-guidelines)。

### SEC EDGAR

- 官方公开 Data APIs 不需要 API Key；请求包含项目名及用户授权的联系邮箱，统一限速为每秒 5 次，低于 SEC 公布的每秒 10 次阈值。[Data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)、[开发者要求](https://www.sec.gov/about/developer-resources)。
- ticker → CIK 使用官方映射，CIK 补足 10 位；读取 submissions、标准 US-GAAP concept 和受限 filing 原文片段。
- 财务事实保留 concept、unit、start/end、form、filed、accession 等，不把提交日当作会计期间。
- Data APIs 的 XBRL 覆盖有范围限制。不得声称它们可以直接提供所有自定义科目、业务分部或“AI 资本支出”。必要时读 filing 原文，缺失则明确不可核验。
- 不混用 GAAP / non-GAAP、季度 / 年度、累计 / 单期、不同单位、修订前后披露。

### Massive（Phase 4 固定供应商）

- 使用用户现有 `MASSIVE_API_KEY` 调用官方 REST，通过本地 FastMCP 暴露三个有界工具：上一交易日 OHLCV、复权日线、公司基本资料。
- 行情标注 `price_type=previous_session_close`、实际交易日、`as_of`、USD、是否复权和 `is_realtime=false`。
- 当前 OHLC 数据中的涨跌字段是同一交易日 close 相对 open，明确标注 `change_basis=close_vs_same_session_open`，不能当作相对前一日收盘价的涨跌。
- 日线请求最多覆盖 730 个日历日；具体可得历史、延迟与字段由套餐和上游响应决定，403/429 等按不可用显示，不补造价格。
- 官方托管 MCP 快速开始采用 OAuth；只有 API Key 不代表托管 MCP 已完成鉴权。此项目采用本地受限 REST 适配，而非让模型调用任意 REST 路径。[Massive REST](https://www.massive.com/docs/rest/quickstart)、[托管 MCP](https://www.massive.com/docs/ai-tools/quickstart)。

### Tavily

- 使用官方远程 MCP，凭证放 Authorization 请求头；只允许 search / extract，不开放 crawl / map。
- search 最多 5 条；extract 最多 3 个公开 HTTPS URL；限制进入模型的内容长度，保留标题、URL、抓取时间和实际片段。
- 搜索结果或抓取成功本身不等于事实核验成功；二手报道、转载和同域网页不得冒充多个独立一手证据。[官方 MCP 文档](https://docs.tavily.com/documentation/mcp)。

## 4. Agent、Runtime 与 Middleware

`create_agent` 使用 Qwen；研究模式只读外部信息并返回 `ReportDraft`；Chat 模式额外允许提出四种个人资料写入。结构化输出使用 `ToolStrategy`，不假设 DashScope 兼容所有供应商原生 JSON Schema 模式。[结构化输出](https://docs.langchain.com/oss/python/langchain/structured-output)、[DashScope 兼容接口](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)。

`RunContext` 注入业务 run_id 和固定本地 user_id。工具使用 `ToolRuntime[RunContext]` 读取 context、tool_call_id 和 Store。模型不能选择用户身份、数据库连接或审批状态。

Middleware 负责：

1. 在模型或工具调用前读取持久预算及取消标记；审批恢复和进程重启不重置计数。
2. 记录实际模型 token 用量；达到软收束阈值后关闭进一步取证，要求生成最终报告。
3. 工具调用前后保存事件；有界处理 MCP `structured_content`，把真实来源登记为 Source 后再交给模型。
4. 区分业务 `available=false`、MCP 工具错误和传输异常；错误不伪装成空数据成功。
5. 只对可重试的只读调用做有限重试；写操作不通过通用重试反复执行。
6. 通过框架原生 HumanInTheLoopMiddleware 暂停个人资料写入。

默认单任务上限：14 次模型调用、18 次工具调用、30 次外部请求、60,000 个总 token、420 秒本次执行时间。研究通常在第 4 轮附近进入收束。token 是调用后上报的，因此最后一次调用可能超过 token 软阈值；该设置不是预付费硬上限。审批后的执行拥有新的单次时间窗口，但累计调用计数延续。

模型上下文只保留完整近期对话轮次及有限文本；完整业务消息仍可分页读取。外部资料均按不可信数据处理，不采纳其中的工具指令或审批要求。[Middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)、[MCP 工具与错误](https://docs.langchain.com/oss/python/langchain/mcp/tools)。

## 5. 证据、断言和报告

报告包含 title、summary、assessment、data_cutoff、claims、sources、positive/negative_factors、uncertainties、follow_up_questions、coverage。

每条原子断言区分 fact / prediction / opinion / inference；记录 ticker、period、unit、explanation。证据条目引用程序发出的 source_id，包含 support / contradict / context、原文 quote 和 rationale。

程序校验与判断：

- source_id 必须属于本次 Run，URL 必须来自实际取证，禁止模型发明引用链接。
- quote 经空白规范化后必须能在已保存 excerpt 中定位；无效引用删除并记警告。
- 预测、意见标记 `not_verifiable`，不声称已经验证未来事件。
- 推论最多 `partially_supported`；同时存在支持和反驳则 `conflicting`。
- X 原帖可证明作者说过什么，不能单独证明作者对外部世界的断言真实。
- 无有效证据为 `insufficient_evidence`；其余可为 supported / contradicted / partially_supported。
- 展示核验来源数、一手来源数、不同域名数和证据标签，不输出未经校准的“准确率”“置信概率”或任意加权 0–100 分。

**实际保证边界：**原文可定位是程序性保证；语义蕴含、事实完整性、时间口径一致、来源独立性仍涉及模型分析和人工审阅。域名不同不等于信息独立，一手来源也可能表达预测。`supported` 是本报告证据状态，不是经统计校准的真值概率。账户画像仅统计已研究样本，不推断整个账号的总体可信率。

`Run.result` 是最终报告唯一序列化事实源；claims/evidence 表用于检索与统计，从最终校验结果写入。不再维护一张容易与 Run.result 分叉的 reports 表。

## 6. 人工审批与记忆

需要审批的 Agent 工具仅四类：add_to_watchlist、save_thesis、update_investment_preferences、update_source_trust。抓取帖子、保存来源、生成研究报告和业务运行日志不需要审批。用户在网页上直接编辑关注列表/设置属于直接操作，界面提交即授权。

使用 PostgreSQL checkpointer 保存原生 interrupt。approvals 保存 run_id、interrupt_id、action_index、tool_call_id、tool_name、args、decision、expires_at。恢复使用框架 `Command(resume=...)`；同一 interrupt 的多个决定收齐后严格按 action_index 排序恢复。[HITL](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)、[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。

- approve 使用原参数，edit 在严格业务 schema 校验后使用新参数，reject 不执行工具。
- 审批决定和工具执行结果分开：approved 不等于 executed。
- 工具执行再次校验 run_id、tool_call_id 和已审批参数，不能绕过界面自行写入。
- 每次写入具有稳定 Operation key；已完成操作重复恢复只返回已有结果。
- stale 决定返回冲突；相同决定重复提交幂等；默认 72 小时过期。
- 取消/失败的 Chat 工具循环使用新的 checkpoint_id，避免未完成工具消息污染下一轮。

短期会话使用 Saver，长期偏好与研究观点使用 Store namespace/key。两个用途不同；V1 不需要向量检索。Store 与 SQLAlchemy 业务表是不同事务，跨库接口不存在天然原子性；采用同一 key 的幂等 upsert 缩小恢复窗口，不声称任意外部副作用“恰好一次”。[持久化](https://docs.langchain.com/oss/python/langgraph/persistence)。

## 7. 数据模型与状态机

业务表：tracked_x_accounts、x_posts、watchlist、chat_threads、research_runs、chat_messages、sources、claims、evidence、approvals、run_events、app_settings、tool_operations、provider_cache、provider_rate_slots、source_profiles。

框架自行管理 checkpoint / store 表；APScheduler 管理自己的 job 表。通过 Alembic 版本化业务迁移，不在生产启动时无条件 drop/create。

Run 状态为 queued → running → awaiting_approval → queued → running，最终为 completed / partial / failed / cancelled / expired。并非每次运行都经过审批。部分来源不可用或预算耗尽为 partial；不得显示为全部成功。每个 Chat thread 同时最多一个活跃 Run，通过数据库唯一约束保证。

queued / running / awaiting_approval 都持久化；Worker 重启把未完成 running 任务重新入队，从保存的输入消息与 checkpoint 判断继续位置。任务执行采用 at-least-once 恢复；进程崩溃在上游读请求完成、checkpoint 保存前时，读请求可能重复且消耗额度。

## 8. API、事件和界面

API 前缀 `/api/v1`；完整请求/响应 schema 由 FastAPI `/docs` 提供。

- health、dashboard：数据库、Worker 心跳、真实统计及最近报告。
- x/accounts CRUD、sync、profile；x/posts 分页筛选、详情、research。
- watchlist CRUD、详情；market/{ticker} quote/history/profile。
- research/runs 创建、列表、详情、cancel、events。
- chat/threads 创建/分页、messages 发送及历史分页。
- approvals 列表/详情、approve/edit/reject；settings 读取/更新；daily-brief 入队。

SSE 从 run_events 按递增 id 回放，支持 Last-Event-ID / after、心跳和终止事件。浏览器断线不取消任务；重连后以 Run 快照为准，事件去重。生成过程文本只作为进度/对话展示，不冒充已经完成校验的最终报告。[SSE 标准](https://html.spec.whatwg.org/multipage/server-sent-events.html)。

七个页面：研究总览、关注列表、X 情报、深度研究、研究对话、待办审批、偏好设置。白色和宝蓝主色；保留加载、无数据、错误、部分完成、等待审批及取消状态；支持手机布局。行情、报告和图表只展示实际数据。

## 9. Worker、调度及配置

独立 Worker 使用数据库 advisory lock，V1 每个数据库仅一个执行 Worker。API 多实例不是本版的扩容承诺。

调度：X 同步默认 60 分钟，简报默认 Asia/Shanghai 08:00，帖子复核每 6 小时；自动帖文研究默认关闭，启用后限有关注标的 cashtag 的帖子、每天最多 2 次。每日简报最多覆盖 5 个关注标的。固定 job ID、replace_existing、coalesce、max_instances=1；调度只入队，研究交给 Worker。[APScheduler 3](https://apscheduler.readthedocs.io/en/3.x/userguide.html)。

配置优先级：进程环境变量 > `.env.local` > `.env`。原有 `.env` 不改写；生成的本地数据库口令、SEC User-Agent 放 `.env.local`。仅从 health/settings 返回配置是否存在，不返回密钥。开发和容器分别使用锁文件安装。

默认只监听 127.0.0.1:8765。绑定非 loopback 必须配置 APP_AUTH_TOKEN；本地 API 限制 Host/Origin。CORS 不是鉴权；此版不宣称具备多租户、角色权限或公网生产防护。模型工具不能访问任意本机路径、SQL 或任意 REST 端点。

## 10. 开发阶段与验收

1. Phase 1：数据库迁移、真实 provider 探测、X 账号→帖子→数据库→页面，限速和分页正确。
2. Phase 2：单 Agent、受限 MCP、原子断言、结构化报告、来源定位；此阶段即接持久 checkpointer，而非等到审批阶段再补。
3. Phase 3：研究对话、Store 记忆、原生 HITL、编辑/拒绝/批量审批顺序、重启恢复和幂等。
4. Phase 4：Massive 日行情、日线、公司资料；SEC 披露、财务事实和原文片段，统一时间及单位标记。
5. Phase 5：持久 Worker/调度、SSE 重连、预算取消、七页 UI、启动脚本、回归测试及验证记录。

验收分层：纯规则单测；新建隔离 PostgreSQL 的真实 checkpoint/Store/API 集成测试；真实凭证能力探测；小额端到端研究；浏览器桌面/手机测试。测试夹具仅出现在 tests 中，不能作为生产数据替身。

不能从少量成功案例推断事实准确率或所有套餐功能可用。Docker 在未安装 Docker 的宿主上只交付配置，不标记为已运行验收。每项实际结果、失败修复及未覆盖范围写入 validation 文档。
