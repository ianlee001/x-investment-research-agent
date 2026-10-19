# 前端视觉重构

本次范围：研究总览、关注列表、X 情报、深度研究、研究对话、待办审批、偏好设置，以及访问口令页面。

## 组件与来源

- HeroUI 3.2.6：Button、Link、Card、Surface、Chip、Modal、CloseButton、Switch、Form、TextField、Input、TextArea、Label、FieldError、SearchField、Select、ListBox、NumberField、Disclosure、Tabs、Pagination、Avatar、ScrollShadow、Alert、Toast、Tooltip、Spinner。与现有 React 19 配合，使用 Tailwind CSS 4；没有引入旧版 Provider 或第二套组件框架。
- 全站表单、搜索、下拉、数字步进、删除/确认操作、页签、分页、折叠来源、反馈提示均使用官方组件。`components/fields.tsx`、`components/Collapsible.tsx` 和 `ui.tsx` 只是对官方组件的项目内组合，统一标签、变体、中文名称和尺寸。`Container` 是 `Surface` 的本地别名，HeroUI 没有名为 Container 的官方组件；用于网格、段落等语义结构的普通 HTML 保留。
- Tremor Raw：按官方复制源码的方式接入 AreaChart，保留 Apache-2.0 许可证与来源说明。底层使用 Recharts 3；本地改动为相对导入、tooltip label 类型兼容、文字大小，以及将图例滚动按钮替换为 HeroUI Button。HeroUI 不提供行情图表，图表继续使用 Tremor。
- 表单校验、标签关联和键盘交互由 HeroUI / React Aria 处理，保留原有 API 与必填/长度/格式限制。行情图表使用现有 Massive bars，缺少行情时显示原有不可用状态。

官方 `heroui-react` Skill 已安装至本机 `.agents/skills/heroui-react`，`heroui-react` MCP 已按 Codex 配置注册。使用 MCP SDK 完成 stdio 初始化、工具列表和实际组件文档读取（服务端 1.1.2）；重新启动 Codex 后可载入其原生 MCP 工具目录。本次组件实现前已读取相关官方文档。

官方资料：

- https://heroui.com/en/docs/react/getting-started/quick-start
- https://heroui.com/en/docs/react/components/modal
- https://heroui.com/en/docs/react/getting-started/agent-skills
- https://heroui.com/en/docs/react/getting-started/mcp-server
- https://github.com/heroui-inc/heroui
- https://www.tremor.so/docs/getting-started/installation
- https://www.tremor.so/docs/visualizations/area-chart
- https://github.com/tremorlabs/tremor

## 视觉与交互

蓝色主题、浅灰工作区和白色内容卡片。正文 16px，辅助文字至少 14px。通过 HeroUI 语义主题变量设置颜色，按钮使用 primary/secondary/ghost/danger 官方变体。导航使用 HeroUI Link 与 `buttonVariants`，通过 render 将其 anchor 与 React Router Link 组合，左上方六个独立胶囊，右上方偏好设置。导航以 `position: fixed` 浮在内容上方，外层透明，不设置整块毛玻璃背景；仅每个未选中胶囊使用半透明背景与 `backdrop-filter`。页面滚动时内容可以经过胶囊后方。

小屏导航横向滑动，当前路由自动进入可视区域，设置保持右上方可用。保留原有路由及键盘链接行为。所有主要操作按钮沿用 HeroUI Button，恢复胶囊圆角。首页“发起研究”进入研究对话。

视觉参考 Apple 的材料规范：https://developer.apple.com/design/human-interface-guidelines/materials 。本项目实现的是 Web CSS 玻璃效果，没有使用或声称等同于原生 SwiftUI Liquid Glass。只在导航功能层使用玻璃效果，报告正文保持实色背景以便阅读。提供减少透明度、减少动态效果和不支持 `backdrop-filter` 时的降级。

自动任务开关切换后立即调用现有设置保存接口，等待响应期间禁止重复修改；失败时回退到之前的开关状态并显示错误。保存成功后更新设置缓存，刷新页面从服务端读取已保存值。普通时间、间隔等输入仍可通过“保存设置”提交。

首页快速输入会带着问题进入研究表单，不会直接发起收费任务。所有页面按需加载，行情图表仅在关注列表加载。原有引用解析、结构化数据快照、流式回答、删除确认、审批和后端接口保留。

新研究表单随右侧面板伸展，桌面端保留一致的内容内边距，手机端避免横向溢出。深度研究和研究对话的记录条目使用覆盖整行的矩形选中背景，并为右侧删除操作预留空间。

本次替换了旧的累计样式，入口仅导入 `src/styles.css`；旧 `readability.css` 不再加载。使用本机字体，不依赖外部字体服务。

## 验证

生产构建：`npm run build`。浏览器回归：`npm test`。

既有测试覆盖七页桌面/手机端可读性与对比度、保存的报告和对话、引用、流式回答、删除流程。新增测试覆盖首页问题传递、弹窗 Tab 焦点约束及 Escape 关闭、Tremor 行情悬浮数值、设置开关关闭后刷新持久化、失败回退、保存期间禁用控件、访问口令登录，以及 1440/1024/768/390px 悬浮导航路由和滚动穿透。HeroUI 迁移回归补充搜索清空、全部状态选项、必填校验阻止无效写入、表单有效载荷、Tabs 键盘切换、NumberField 步进；下拉测试通过实际弹层和选项操作，不使用原生 selectOption。颜色检查由浏览器 canvas 将 oklch/color-mix 解析为 sRGB，再计算 WCAG 对比度。

测试中的增删改和模型相关操作均通过隔离请求模拟；真实数据验证只读保存的记录，行情显示测试使用独立 fixture，不额外调用外部行情服务。
