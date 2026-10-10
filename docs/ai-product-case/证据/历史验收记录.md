# V1 验收记录

日期：2026-10-08。以下区分实际调用、测试夹具与未验证能力；不将构建成功当作所有功能正确。

## 已完成的真实验证

- 使用现有凭证验证 DashScope Qwen 工具调用、结构化结果和流式输出；Tavily 官方远程 MCP 工具发现；X 用户/帖子读取；SEC NVDA filings；Massive NVDA 上一交易日行情。结果摘要保存在不含密钥的 `.runtime/provider-checks.json`。
- 实际 PostgreSQL 17.11 运行于本机 55432；业务 Alembic 迁移与框架 checkpoint / Store 建表已执行。数据库口令仅保存在忽略的 `.env.local`。
- 真实研究 `fbdced81-f8f9-4412-8f5a-85e837be9436` 完成：4 次模型调用、4 次工具调用、4 次直接外部请求、32,657 tokens、3 条断言、4 个来源；引用定位警告为 0。此为单个受限案例，不是准确率评估。
- 该报告在真实浏览器中打开，逐条断言与保存来源均可显示。
- 实际 X 入库：公开 `@nvidia` 的 5 条帖子经官方 API 读取、规范化并存入业务库，在手机和桌面页面展示。初次回填仅 1 页 5 条，保留真实账号作为已验证样例，可在情报页面移除追踪。
- 实际 Qwen HITL：Run `e555abd5-f1af-4f22-abc1-057db148274f` 提出 add_to_watchlist，暂停于审批；停止并重新启动应用后，审批 ID `3f072ee1-0397-4a25-93f8-4257a83d86a9` 保持一致；提交拒绝后正常恢复并 completed，execution_status 为 not_executed。2 次模型调用、6,243 tokens。没有自动批准个人资料修改；批准/编辑后的执行在隔离库验证。
- 项目启动/停止脚本已实际执行：隐藏 API/Worker，停止已记录进程及 Python 子进程后确认 8765 端口释放；重新启动后数据库和待审批状态仍在。

## 回归覆盖

后端测试在自动创建的隔离 PostgreSQL 中运行，覆盖：预测/意见与推论规则、冲突证据、伪造来源及引文、X 自证限制、ticker/schema；原生 interrupt→数据库保存→重新创建 Agent→编辑恢复；多操作审批顺序、拒绝不执行、重复提交幂等、工具执行与审批状态分离、跨 Store 连接读取；X 增量分页水位和部分错误；API 幂等冲突、Origin 限制、SSE 游标回放。

浏览器测试覆盖七个页面、真实报告引用显示、390px 手机导航与横向溢出。最终执行计数见本文件末尾的完成记录。

## 联调中修复的问题

1. 配置根目录曾少向上一层，修正为读取项目 `.env` / `.env.local`。
2. Windows 默认 Proactor loop 不适配所用 psycopg async 路径，CLI 明确使用 Selector loop。
3. 显式工具 args_schema 将 Runtime 注入字段当成多余输入，导致通过审批却未写入；改为隐藏 Runtime 的工具 schema 推导，并在执行边界严格校验业务参数。
4. 初次真实研究耗尽 token 预算而未生成最终结构化报告；限制工具结果长度并加入收束轮次，修复后的上述真实研究成功。原失败/部分完成记录保留，不掩盖结果。
5. 相同幂等键不能用于不同请求；X 部分错误不推进增量游标。
6. Chat 取消/失败后轮换检查点，避免未完成工具调用影响下一轮。
7. 端口 8000 已被其他程序占用，项目使用 8765，没有停止其他程序。

## 保证边界与尚未验证

- 引文定位不等于语义蕴含；模型可误解上下文。当前没有人工标注大样本、事实准确率或校准置信概率。
- 真实数据源验证证明当时所测端点可用，不能证明其他套餐、实时行情、全历史 X 搜索或任意 SEC 自定义财务概念可用。
- MCP 适配使用锁定的 beta API；依赖升级需要重新运行协议和审批测试。
- 外部只读调用在崩溃窗口可能重复并计费；长期 Store 与业务表不属于同一 SQLAlchemy 事务，采用幂等 key 恢复。
- 单个 Worker、单用户本地部署；未进行多租户、公网渗透或高并发负载验收。
- 宿主未安装 Docker，未实际执行容器构建/启动；交付 Dockerfile/compose 供具备环境时验证。
- 自动定时简报、同步和复核已实现，验收不等同于数周连续运行稳定性证明；停机期间不会执行远程复核。

## 完成记录

| 检查 | 实际结果 |
|---|---|
| `ruff check backend scripts tests` | 通过 |
| `ruff format --check backend scripts tests` | 通过 |
| `pytest --integration -q` | 20 项通过，包含 Alembic 空库迁移、降级/再升级，以及 X 内容撤回后的证据/事件/checkpoint 清理 |
| `npm run build` | TypeScript 检查及 Vite 生产构建通过 |
| `npm test` | 两项 Playwright 浏览器验收通过，覆盖七页、真实报告、手机导航及对话切换入口 |
| provider 实时探测 | DashScope、Tavily、X、SEC、Massive 五项通过 |
| 小额真实研究 | 完成，3 断言、4 来源、0 引文定位警告 |
| 真实模型审批重启恢复 | 通过拒绝分支，个人关注列表未被测试写入 |
| Docker | 未执行；本机无 Docker |

浏览器截图保存在 `.runtime/dashboard-desktop.png`、`.runtime/research-desktop.png` 和 `.runtime/intelligence-mobile.png`。当前保留 LangChain MCP beta 提示；锁定版本可运行，不表示该接口已稳定。

## 界面可读性修订（2026-10-08）

- 七个页面统一深色文字；正文、帖子、报告、对话及输入框使用 16px，辅助文字至少 14px。手机端不再缩小字体。
- 清理宣传区、重复副标题、英文装饰标签和常驻功能解释；保留来源、行情日期、单位、审批期限及实际影响操作的提示。报告说明和运行详情折叠展示。
- 调整按钮、开关、表单和手机布局；时区完整显示，页面没有横向溢出。
- `npm run build` 通过；`npm test` 共 6 项通过。浏览器覆盖 1440px 与 390px 七个页面、已有真实报告和对话、添加标的与审批编辑弹窗。
- 自动检查实际渲染文字和输入框占位文字的对比度至少 4.5:1、字号至少 14px，并检查页面横向溢出；结合截图人工查看。对比度阈值参照 [W3C WCAG 2.2 Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)，不等于完整 WCAG 合规审计。
- 股票已填充状态与待审批弹窗使用浏览器隔离夹具，不写入业务数据库；浏览器检查拦截行情请求，避免消耗外部 API 额度。截图保存在 `.runtime/readability-*.png`。
