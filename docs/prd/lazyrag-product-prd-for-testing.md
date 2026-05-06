# LazyRAG 产品 PRD（测试版）

文档版本：v1.0
编写日期：2026-04-29
适用对象：产品、研发、测试
覆盖模块：数据源管理、算法跃迁、智积阅累

## 1. 文档说明

本文档用于给测试同学梳理 LazyRAG 当前前端产品能力、核心流程、接口依赖、验收标准和用例设计重点。内容以当前仓库实现为基准整理。

模块入口：

- 数据源管理：`/data-sources`
- 算法跃迁：`/self-evolution`
- 智积阅累：`/memory-management`

## 2. 数据源管理

### 2.1 背景与目标

数据源管理用于将本地目录或飞书空间/文件夹接入 LazyRAG 知识库体系，并通过扫描 Agent 完成文件发现、增量识别、任务生成、解析入库和同步状态追踪。

测试目标：

- 验证数据源创建、编辑、连接测试、列表刷新、详情查看和手动拉取流程可用。
- 验证本地目录与飞书数据源在权限、配置项、同步策略、错误提示上的差异。
- 验证文档变更状态、解析状态、同步统计和目录树筛选选择逻辑准确。

### 2.2 入口与权限

- 菜单入口：数据管理 / 数据源管理。
- 列表页：`/data-sources`
- 详情页：`/data-sources/:id`
- 飞书 OAuth 回调页：`/oauth/feishu/data-source/callback`
- 本地目录数据源标记为管理员可用。
- 飞书数据源需要先配置 App ID / App Secret，配置完成后才允许选择。

### 2.3 功能范围

列表页展示全局概览和数据源表格。

概览卡片：

- 数据源总数。
- 运行中数据源数。
- 已解析文档总数。
- 异常/告警数据源数。

表格字段：

- 数据源名称与类型。
- 同步模式：手动或定时。
- 连接状态：已连接、待连接、已过期、异常。
- 文档数。
- 最近同步时间。
- 新增、删除、变更统计。
- 操作：查看详情、编辑配置。

列表操作：

- 新建数据源。
- 刷新列表。
- 查看详情抽屉或进入详情页。
- 编辑已有数据源配置。

### 2.4 新建/编辑向导

向导分两步。

第 1 步：选择数据源类型。

- 本地目录：选择后进入本地目录配置。
- 飞书：未配置 App ID / App Secret 时置灰并提示；已配置后可选择。

第 2 步：填写配置。

公共配置：

- 知识库名称：必填。
- 同步模式：定时同步、手动同步。

本地目录配置：

- 访问路径：必填，例如 `/mnt/team-share/ops-docs`。
- 连接测试：调用扫描 Agent 校验路径可访问。
- 定时周期：每日、每 2 天、每周。
- 同步时间：`00:00`、`02:00`、`06:00`、`23:00`。

飞书配置：

- 飞书 App ID / App Secret：用于发起 OAuth。
- 授权账号：通过 OAuth 弹窗连接账号，支持手动粘贴回调结果。
- 目标类型：Wiki 空间或云盘文件夹。
- 目标标识：必填。
- 定时周期：每日。
- 同步时间：`00:00`、`02:00`、`06:00`、`23:00`。

保存前置条件：

- 已选择数据源类型。
- 飞书类型已完成 App 配置。
- 已完成连接测试或 OAuth 连接验证。
- 必填字段已通过表单校验。

### 2.5 保存逻辑

本地数据源创建：

1. 获取扫描 Agent 列表。
2. 调用 Core 获取可用知识库算法。
3. 创建知识库。
4. 创建扫描 Source。
5. 根据同步模式启用或关闭 watch。
6. 刷新列表并提示“数据源已创建”。

本地数据源编辑：

1. 更新 Source 名称、根路径、扫描间隔、空闲窗口。
2. 根据同步模式启用或关闭 watch。
3. 刷新列表并提示“数据源配置已更新”。

飞书数据源创建/编辑：

1. 获取扫描 Agent 列表。
2. 调用 Core 获取可用知识库算法。
3. 必要时创建知识库和 Source。
4. 绑定飞书云端配置，包括授权连接、目标类型、目标标识、include/exclude 规则、对象大小限制、定时表达式。
5. 触发一次手动云同步。
6. 轮询云同步运行状态，成功或部分成功后刷新列表。

飞书默认同步规则：

- Include：`**/*.md`、`**/*.doc`、`**/*.docx`、`**/*.pdf`、`**/*.txt`
- Exclude：`**/~$*`
- 最大对象大小：200 MB。
- 云同步后默认触发 reconcile。

异常场景：

- 没有可用扫描 Agent：提示“未发现可用扫描 Agent，请先启动并注册扫描 Agent。”
- 没有可用知识库算法：提示检查 Core 服务算法配置。
- Source 创建成功但未返回 id：提示无法配置监听状态。
- 云同步失败、错误、取消：展示云同步错误信息。
- 云同步超过 120 秒未完成：提示等待飞书目录同步超时。

### 2.6 详情与手动拉取

详情页展示：

- 数据源名称、状态标签、最近同步时间。
- 同步路径、已解析文档数、存储占用。
- 新增、变更、删除、待同步、总文件数。
- 文档表格：文件名、路径、大小、标签、更新状态、同步说明、解析状态、源端更新时间、系统更新时间。
- 关键字搜索：匹配文件名、路径、同步说明。

手动拉取流程：

1. 点击详情页“立即同步”。
2. 加载 Agent 目录树。
3. 默认选中有更新的文件。
4. 支持按关键字筛选目录树。
5. 支持按状态筛选：有更新、未变化。
6. 支持选择全部筛选结果或清空选择。
7. 确认后生成部分同步任务。
8. 飞书数据源先触发云同步，再生成任务。
9. 展示已检查、已同步、已忽略数量。

同步后表现：

- 已同步的新增/变更文件更新为未变化和已解析。
- 已同步的删除文件从当前列表移除。
- 更新最近同步时间。
- 展示最近一次手动拉取结果。
- 若仍有解析中的任务，详情页继续轮询刷新。

### 2.7 关键接口

- `GET /api/scan/agents`
- `POST /api/scan/agents/fs/validate`
- `GET /api/scan/sources`
- `POST /api/scan/sources`
- `GET /api/scan/sources/{id}`
- `PUT /api/scan/sources/{id}`
- `POST /api/scan/sources/{id}/watch/enable`
- `POST /api/scan/sources/{id}/watch/disable`
- `GET /api/scan/sources/{id}/documents`
- `POST /api/scan/sources/{id}/tasks/generate`
- `POST /api/scan/agents/fs/tree`
- `GET /api/scan/sources/{id}/cloud/binding`
- `POST /api/scan/sources/{id}/cloud/binding`
- `POST /api/scan/sources/{id}/cloud/sync/trigger`
- `GET /api/scan/sources/{id}/cloud/sync/runs`
- `GET /api/core/dataset/algos`
- `POST /api/scan/knowledge-bases`

### 2.8 验收与测试建议

验收标准：

- 列表页可看到概览统计和数据源表格；接口失败时页面有可理解提示。
- 新建本地数据源时，未填写访问路径不可保存；连接测试未通过不可保存。
- 新建飞书数据源时，未配置 App ID / App Secret 不可选择飞书；未授权账号不可保存。
- 编辑数据源时，原配置正确回填；修改路径或飞书目标后连接状态应重新变为待验证。
- 定时同步与手动同步切换后，保存应调用对应 watch 或 cloud binding 配置。
- 详情页可展示文档状态，关键字筛选只影响表格展示。
- 手动拉取空选择时不可提交；有选择时可生成任务并展示结果。

测试建议：

- 本地数据源：创建成功、路径为空、路径不可访问、无 Agent、编辑后关闭定时同步。
- 飞书数据源：未配置 App、OAuth 成功、OAuth 失败、手动回调成功、目标标识为空、云同步超时。
- 列表：刷新、状态映射、异常数据源告警计数、操作入口跳转。
- 详情：文档状态映射、解析状态映射、搜索、目录树筛选、选择全部、清空选择、部分同步。

非本期范围：

- S3、Confluence、Notion 类型虽然存在类型定义，本期页面入口未开放。
- 数据源删除能力未在当前页面提供。

## 3. 算法跃迁

### 3.1 背景与目标

算法跃迁是 LazyRAG 的自进化执行控制台，用于围绕指定知识库启动一轮优化流程。系统通过“生成数据集、评测报告、分析报告、代码优化、A/B 测试”五步编排，帮助算法和研发人员定位效果问题、生成改进建议并验证收益。

测试目标：

- 验证启动配置、会话工作台、执行步骤展示和事件流接收。
- 验证知识库选择、评测集策略、补充评测集策略和过程干预模式的约束。
- 验证数据集、评测图表、分析报告、代码 Diff、A/B 对比展示可用。

### 3.2 入口与权限

- 菜单入口：算法跃迁。
- 路由：`/self-evolution`
- 仅管理员且开发者模式开启时显示入口。
- 非管理员或未开启开发者模式时访问该路由应被导航逻辑拦截。

### 3.3 启动配置

用户进入页面后，先完成 4 个启动配置项，再点击第 5 步“开始”。

配置项：

1. 选择知识库：必选，用作本轮优化目标。
2. 已有评测集：当前仅支持“不使用已有评测集”。
3. 补充评测集：当前固定为“是，补充评测集”。
4. 过程干预：自动处理或交互处理。
5. 开始：确认后启动本轮优化。

知识库加载：

- 页面初始化时调用知识库列表接口，展示所有可用知识库。
- 加载中展示“正在加载知识库”。
- 加载失败展示“知识库加载失败”，下拉中提供点击重试。
- 无数据时展示“暂无可用知识库”。

启动校验：

- 未选择知识库不可开始，提示“必须先选择知识库才可以开始。”
- 未选择评测集策略不可开始。
- 未选择补充评测集策略不可开始。
- 未选择过程干预方式不可开始。
- 当“不使用已有评测集”时，必须补充生成评测集。

### 3.4 启动接口与事件流

点击开始后：

1. 创建 Agent Thread。
2. 调用 Thread start 接口启动流程。
3. 成功后进入工作台。
4. 订阅线程事件流，持续接收执行进度。

创建线程请求关键信息：

- `mode`：`auto` 或 `interactive`。
- `title`：知识库名称。
- `inputs.kb_id`：所选知识库 id。
- `inputs.algo_id`：`general_algo`。
- `inputs.eval_name`：评测集名称。
- `inputs.num_cases`：当前默认 1。
- `inputs.target_chat_url`：自进化评测目标服务地址。
- `inputs.dataset_name`：`algo`。

接口依赖：

- `GET /api/core/datasets` 或等价知识库列表接口。
- `POST /api/core/agent/threads`
- `POST /api/core/agent/threads/{threadId}:start`
- `GET /api/core/agent/threads/{threadId}:events`

事件流规则：

- 事件流连接成功后，在会话中追加线程 ID。
- 解析 SSE 帧中的 `message`、`content`、`text`、`kind`、`event_name` 或原始数据作为摘要。
- 收到 `thread.stop` 后停止读取。
- 连接失败时提示检查 SSE 接口。

### 3.5 工作台与五步内容

启动后进入双栏工作台。

左侧：自进化执行编排。

- Step 1 生成数据集：进行中。
- Step 2 评测报告：待执行。
- Step 3 分析报告：待执行。
- Step 4 代码优化：待执行。
- Step 5 A/B 测试：待执行。

右侧：历史会话窗口。

- 会话标签列表。
- 当前会话消息流。
- 输入框继续发送指令。
- 支持切换知识库和处理模式。
- 支持新建会话。

五步展示内容：

- Step 1 生成数据集：展示数据集明细表，字段包括序号、问题类型、问题、标准答案、参考文档、参考上下文、关键点；支持下载当前数据集 JSON。
- Step 2 评测报告：展示答案正确性、忠实性、上下文召回、文档召回；单分类展示饼图，多分类展示折线图。
- Step 3 分析报告：展示 Markdown 格式分析报告。
- Step 4 代码优化：展示 Unified Diff，支持文件树、文件切换、增删行统计和代码内容预览。
- Step 5 A/B 测试：展示基线与实验组指标对比；单分类展示分组柱状图，多分类展示按指标分面的分组柱状图。

当前步骤操作按钮为待联调态，点击后提示对应步骤操作已加入待联调。

### 3.6 会话能力

发送指令：

- 输入框为空时发送按钮禁用。
- Enter 发送，Shift + Enter 换行。
- 未选择知识库时不可发送，提示必须选择知识库才可以生成数据集。
- 第一次发送后进入工作台，并追加用户消息和助手消息。
- 后续发送继续追加上下文消息。

新建会话：

- 点击“新建”打开五步配置弹窗。
- 需要重新选择知识库、评测集策略、补充策略和处理模式。
- 配置不完整时不可确认。
- 确认后创建新会话标签，切换到新会话并进入工作台。

关闭会话：

- 至少保留一个会话标签。
- 关闭当前会话后自动切换到剩余第一个会话。

### 3.7 验收与测试建议

验收标准：

- 非管理员或未开启开发者模式时，不应看到或进入算法跃迁入口。
- 页面初始化应正确加载知识库列表，加载中、失败、空列表状态可辨识。
- 未选择知识库时，“开始”按钮不可用或点击后有明确提示。
- 启动成功后应创建线程、启动线程并进入工作台。
- 事件流连接成功后应展示线程 ID 和后续事件摘要。
- SSE 失败时应提示连接失败，不影响页面继续操作。
- 五步卡片状态、标题、说明和折叠内容展示正确。
- 数据集下载文件名和 JSON 内容可用。
- 输入框空值不可发送；Enter 和 Shift + Enter 行为符合预期。
- 新建会话、切换会话、关闭会话状态正确。

测试建议：

- 权限：管理员/非管理员、开发者模式开/关。
- 启动配置：知识库加载成功、失败、空列表、点击重试。
- 启动接口：创建 thread 成功但缺少 thread_id、start 失败、事件流失败。
- 事件流：普通事件、无法解析 JSON、`thread.stop`。
- 工作台：五步折叠内容、下载数据集、图表空数据、单分类和多分类。
- 会话：首次发送、连续发送、新建会话、关闭最后一个会话限制。

非本期范围：

- 五步执行按钮的真实后端联动当前为待联调提示。
- 数据集、评测报告、分析报告、代码 Diff、A/B 报告当前包含模拟数据展示。

## 4. 智积阅累

### 4.1 背景与目标

智积阅累用于管理 LazyRAG 的长期能力资产，包括术语词表、技能、用户经验/偏好和内置工具说明。模块支持资产增删改查、技能分享、AI 演化建议审核、草稿预览确认，以及术语合并与建议处理。

测试目标：

- 验证四类资产的列表、筛选、查看、新增、编辑、删除和详情能力。
- 验证技能和经验的演化建议审核流程。
- 验证术语词表的查重、合并、批量删除和建议收件箱。
- 验证技能分享与接收处理流程。

### 4.2 入口与资产类型

主路由：`/memory-management`

子路由：

- 工具：`/memory-management/tools`
- 技能：`/memory-management/skills`
- 经验：`/memory-management/experience`
- 术语：`/memory-management/glossary`
- 术语详情：`/memory-management/glossary/:itemId`
- 建议审核：`/memory-management/review/:tab/:itemId`

默认标签顺序：

1. 术语。
2. 技能。
3. 经验。
4. 工具。

工具：

- 工具为系统内置只读资产，用于说明 Agent 可调用工具。
- 当前包括 `kb_search`、`kb_get_parent_node`、`kb_get_window_nodes`、`kb_keyword_search`、`memory`、`skill_manage`、`get_skill`、`read_reference`、`run_script`、`read_file`、`list_dir`、`search_in_files`、`make_dir`、`write_file`、`delete_file`、`move_file`、`shell_tool`、`download_file`。
- 工具可查看，不允许新增、编辑、删除、分享。

技能：

- 字段包括名称、描述、分类、标签、父技能、子技能、内容、是否保护、文件扩展名、是否启用、更新状态/建议状态。
- 能力包括列表加载、查看详情、新增、编辑、删除、上传技能文件、添加子技能、分享技能、查看分享状态、处理收到的分享、打开演化建议审核。

经验：

- 字段包括标题、内容、是否保护、资源类型、建议状态。
- 能力包括列表加载、查看、新增、编辑、删除、开关个性化能力、分享链接、打开演化建议审核。

术语：

- 字段包括术语、分组、别名、来源、内容说明、是否保护。
- 字段限制：术语名最大 50 字符，单个别名最大 50 字符，内容说明最大 300 字符。
- 能力包括列表加载、关键字搜索、来源筛选、详情页、新增、编辑、删除、批量删除、批量合并、查重、处理 AI 建议。

### 4.3 技能上传与分享

上传规则：

- 父技能上传支持 `.md`、`.markdown`。
- 普通技能上传支持 `.md`、`.markdown`、`.txt`、`.json`、`.yaml`、`.yml`。
- Markdown front matter 支持识别 `name` 和 `description`。
- 上传 Markdown 且已有表单内容时，需要确认是否用文件元数据覆盖。

分享对象：

- 用户。
- 用户组。

分享规则：

- 至少选择一个用户或用户组。
- 技能分享调用后端分享接口。
- 分享后可刷新查看分享状态。
- 支持复制分享链接，链接携带 `tab` 和 `item` 参数。

分享中心：

- 收到的分享：只展示可操作状态，如 pending、unknown。
- 发出的分享：展示已发出记录。
- 收到的分享支持预览、接受、拒绝。
- 接受后刷新技能列表和分享中心。

### 4.4 术语查重与合并

查重规则：

- 保存新建或编辑术语前，调用词表查重接口。
- 检查对象包括术语名和别名。
- 存在冲突时应阻止或提示用户处理。

批量合并：

- 至少选择 2 个术语。
- 默认第一个为主词条，其余作为合并来源。
- 合并时汇总来源词条的术语、别名和说明。
- 用户可在编辑弹窗中确认最终内容。
- 保存后调用合并接口，再更新合并后的词条内容。

### 4.5 演化建议审核

技能和经验支持进入建议审核页。

触发入口：

- 列表中带待审核状态的技能或经验。
- `/memory-management/review/skills/:itemId`
- `/memory-management/review/experience/:itemId`

审核能力：

- 查看原始资产。
- 查看建议列表。
- 按字段展示差异。
- 单条接受或拒绝建议。
- 批量接受或拒绝建议。
- 加载更多后端建议。
- 根据已接受建议生成草稿。
- 预览草稿 diff。
- 编辑预览内容。
- 确认草稿或丢弃草稿。

后端建议状态：

- 接受：调用 approve 接口。
- 拒绝：调用 reject 接口。
- 批量接受/拒绝：调用 batch 接口。
- 已处理建议应从当前建议列表移除或标记为已审核。

草稿规则：

- 技能建议生成技能草稿。
- 经验建议根据资源类型生成 `memory` 或 `user-preference` 草稿。
- 确认草稿后刷新对应资产列表。
- 离开审核页时，如存在未确认草稿，需要确认是否丢弃。

### 4.6 关键接口

技能：

- `GET /api/core/skills`
- `GET /api/core/skills/{skillId}`
- `POST /api/core/skills`
- `PATCH /api/core/skills/{skillId}`
- `DELETE /api/core/skills/{skillId}`
- `POST /api/core/skills/{skillId}:generate`
- `GET /api/core/skills/{skillId}:draft-preview`
- `POST /api/core/skills/{skillId}:confirm`
- `POST /api/core/skills/{skillId}:discard`
- 技能分享相关接口：分享、分享详情、收到列表、发出列表、接受、拒绝、分享目标状态。

经验/偏好：

- `GET /api/core/personalization-items`
- `GET /api/core/personalization-setting`
- `PUT /api/core/personalization-setting`
- `PUT /api/core/user-preference`
- `PUT /api/core/memory`
- `GET /api/core/evolution/suggestions`
- `GET /api/core/evolution/suggestions/{suggestionId}`
- `POST /api/core/evolution/suggestions/{suggestionId}:approve`
- `POST /api/core/evolution/suggestions/{suggestionId}:reject`
- `POST /api/core/evolution/suggestions:batchApprove`
- `POST /api/core/evolution/suggestions:batchReject`
- `POST /api/core/user-preference:generate`
- `GET /api/core/user-preference:draft-preview`
- `POST /api/core/user-preference:confirm`
- `POST /api/core/user-preference:discard`
- `POST /api/core/memory:generate`
- `GET /api/core/memory:draft-preview`
- `POST /api/core/memory:confirm`
- `POST /api/core/memory:discard`

术语：

- `GET /api/core/word_group`
- `POST /api/core/word_group:search`
- `GET /api/core/word_group/{groupId}`
- `POST /api/core/word_group`
- `POST /api/core/word_group:update`
- `DELETE /api/core/word_group/{groupId}`
- `POST /api/core/word_group:batchDelete`
- `POST /api/core/word_group:merge`
- `POST /api/core/word_group:checkExists`

### 4.7 验收与测试建议

验收标准：

- 各子路由可直接访问，并能正确激活对应标签。
- 工具列表为只读，筛选和查看可用。
- 技能列表能加载、查看、新增、编辑、删除；删除前有确认。
- 技能文件上传能正确识别格式、读取内容和 front matter。
- 技能分享至少选择一个目标；分享成功后状态可刷新。
- 收到的技能分享可预览、接受、拒绝；接受后技能列表刷新。
- 经验列表能加载、开关个性化能力、新增、编辑和保存。
- 术语列表支持关键字、来源筛选、详情页、查重、批量删除和批量合并。
- 演化建议审核支持单条和批量接受/拒绝，生成草稿、预览草稿、确认和丢弃。
- 接口失败时应展示错误提示，不应造成页面状态混乱。

测试建议：

- 路由：从列表、详情、审核页刷新浏览器后状态恢复。
- 技能：空列表、树形父子技能、上传各种后缀、同名子技能、删除有待审核建议的技能。
- 分享：无目标提交、用户分享、用户组分享、复制链接、收到分享接受/拒绝。
- 经验：个性化开关成功/失败、front matter 解析异常、保存后刷新。
- 术语：字段长度边界、别名去重、查重冲突、批量合并、批量删除、AI 建议接受/拒绝。
- 审核：无建议、加载更多、建议已过期、单条审核、批量审核、草稿确认、离开时丢弃确认。

非本期范围：

- 工具资产的新增、编辑、删除。
- 技能分享的权限继承细则和跨租户策略。
- 术语建议生成逻辑本身。
