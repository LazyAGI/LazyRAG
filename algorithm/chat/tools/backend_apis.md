# 算法依赖的后端接口 — skill / memory / user_preference 写入

本文档定义**算法侧在会话运行中直接调用的业务后端 HTTP 接口**。算法在这些接口上是 client，后端是 server，负责落库、入队、人审、合入 / 删除等所有有状态操作。

覆盖三类持久文本资源（skill / memory / user_preference）共 5 个接口：

| 接口 | 用途 | 对应算法侧工具 |
|------|------|----------------|
| `POST /skill/suggestion` | 对已有 skill 提交修改建议 | `skill_manage(name, action='modify', category=..., suggestions=...)` |
| `POST /skill/create` | 新建 skill | `skill_manage(name, action='create', category=..., content=...)` |
| `POST /skill/remove` | 删除 skill | `skill_manage(name, action='remove', category=...)` |
| `POST /memory/suggestion` | 记录 agent memory 修改建议 | `memory(target='memory', suggestions=...)` |
| `POST /user_preference/suggestion` | 记录用户偏好修改建议 | `memory(target='user', suggestions=...)` |

> **算法侧是无状态的**：算法不维护任何 pending 列表或历史；本文档中的接口全部一次一传，持久化、状态流转、人审入队、实际合入 / 删除一律由后端负责。

所有接口契约与 `chat/tools/skill_manager.py`、`chat/tools/memory.py` 中的工具定义保持一致。skill 相关的三个接口在算法侧统一通过 `skill_manage(name, action, ...)` 工具触发：

| `action` | 对应 HTTP 接口 | 存在性约束（基于用户**全量** skill 列表） |
|----------|----------------|-------------------------------------------|
| `create` | `POST /skill/create`     | (`category`, `skill_name`) 必须**不存在** |
| `modify` | `POST /skill/suggestion` | (`category`, `skill_name`) 必须**已存在** |
| `remove` | `POST /skill/remove`     | (`category`, `skill_name`) 必须**已存在** |

> 存在性校验以用户的**全量 skill 列表**为准，不是 agent 的 `available_skills` 白名单；算法侧通过远端 skill 文件系统读取全量目录。`category` 取 skill 路径中 `skill_name` 的直接上一层目录；若 `/skills/` 之后先出现 UUID 样式的 user_id 目录，需要忽略该段。

---

## 通用约定

| 项目 | 说明 |
|------|------|
| Method | `POST` |
| Content-Type | `application/json` |
| 鉴权 | 沿用现有会话鉴权方案 |
| `session_id` | 全部 5 个接口均为必填 |
| 单次上限 | `suggestions` 列表长度 **≤ 5** |
| 错误处理 | 非 2xx 代表请求失败；body 遵循[通用响应体](#通用响应体) |

---

## Suggestion 结构

`/skill/suggestion`、`/memory/suggestion`、`/user_preference/suggestion` 共用下述 `Suggestion` 结构，均为自然语言形式；由下游 reviewer 理解并应用。

```jsonc
{
  // 建议的简短标题，必填
  "title": "补充 rebase 代替 merge 的规范",

  // 自然语言描述的修改建议，必填
  "content": "在 Git Workflow 章节加入：团队内优先使用 rebase 保持提交线性，仅在跨团队协作时使用 merge。",

  // 提议理由，可选
  "reason": "近期多次出现 merge commit 污染主干历史"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | `string` | 是 | 建议标题，用于 review 列表速览 |
| `content` | `string` | 是 | 自然语言描述的修改建议 |
| `reason` | `string` | 否 | 提议理由 |

---

## 写入建议接口

### 1. `POST /skill/suggestion` — 记录 skill 修改建议（action='modify'）

仅用于对**已存在**的 skill 提出修改建议。skill 的新增 / 删除请分别走 [`/skill/create`](#2-post-skillcreate--新建-skill-actioncreate) 与 [`/skill/remove`](#3-post-skillremove--删除-skill-actionremove)。

**Request Body**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | `string` | 是 | 会话 ID |
| `category` | `string` | 是 | 目标 skill 的分类目录，与 `skill_name` 一起唯一标识一个 skill |
| `skill_name` | `string` | 是 | 目标 skill 名（必须为已存在的 skill） |
| `suggestions` | `Suggestion[]` | 是 | 建议列表，长度 **≤ 5** |

**请求示例**

```json
{
  "session_id": "sess-abc",
  "category": "engineering",
  "skill_name": "git-workflow",
  "suggestions": [
    {
      "title": "补充 rebase 规范",
      "content": "在 Git Workflow 章节加入：团队内优先使用 rebase 保持提交线性。",
      "reason": "近期多次出现 merge commit 污染主干历史"
    }
  ]
}
```

**校验规则**

- `len(suggestions) > 5` → `400`；
- 字段类型 / 必填缺失 → `400`；
- (`category`, `skill_name`) 对应 skill 不存在 → `404`（由后端决定是否改为引导调用 `/skill/create`）。

---

### 2. `POST /skill/create` — 新建 skill（action='create'）

**Request Body**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | `string` | 是 | 会话 ID |
| `category` | `string` | 是 | 新建 skill 的分类目录 |
| `skill_name` | `string` | 是 | 新建 skill 的名称（必须是当前不存在的 skill） |
| `content` | `string` | 是 | 新 skill 的完整 SKILL.md 正文（非空） |

**请求示例**

```json
{
  "session_id": "sess-abc",
  "category": "engineering",
  "skill_name": "git-workflow",
  "content": "# Git Workflow\n\n## Commit\n- 团队内优先使用 rebase 保持提交线性。\n"
}
```

**校验规则**

- `content` 缺失 / 为空字符串 → `400`；
- (`category`, `skill_name`) 已存在 → `409`（由后端定义，亦可要求 Agent 改走 `/skill/suggestion`）；
- 字段类型 / 必填缺失 → `400`。

> 注意：本接口**不接受 `suggestions` 字段**；创建语义下传入 suggestions 视为 `400`。

---

### 3. `POST /skill/remove` — 删除 skill（action='remove'）

**Request Body**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | `string` | 是 | 会话 ID |
| `category` | `string` | 是 | 目标 skill 的分类目录，与 `skill_name` 一起唯一标识一个 skill |
| `skill_name` | `string` | 是 | 目标 skill 名（必须为已存在的 skill） |

**请求示例**

```json
{
  "session_id": "sess-abc",
  "category": "engineering",
  "skill_name": "git-workflow"
}
```

**校验规则**

- (`category`, `skill_name`) 不存在 → `404`；
- 字段类型 / 必填缺失 → `400`；
- 请求体中出现 `content` 或 `suggestions` → `400`（删除语义不接受任何正文字段）。

---

### 4. `POST /memory/suggestion` — 记录 agent memory 写入建议

**Request Body**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | `string` | 是 | 会话 ID |
| `suggestions` | `Suggestion[]` | 是 | 建议列表，长度 **≤ 5** |

**请求示例**

```json
{
  "session_id": "sess-abc",
  "suggestions": [
    {
      "title": "记录用户语言偏好",
      "content": "在 memory 中追加一条：该用户偏好用简体中文交流。",
      "reason": "跨会话稳定偏好"
    }
  ]
}
```

**校验规则**

- `len(suggestions) > 5` → `400`；
- 字段类型 / 必填缺失 → `400`。

---

### 5. `POST /user_preference/suggestion` — 记录用户偏好写入建议

**Request Body**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | `string` | 是 | 会话 ID |
| `suggestions` | `Suggestion[]` | 是 | 建议列表，长度 **≤ 5** |

**请求示例**

```json
{
  "session_id": "sess-abc",
  "suggestions": [
    {
      "title": "提交前不自动 push",
      "content": "记录用户习惯：在 commit 后不应自动执行 push。"
    }
  ]
}
```

**校验规则**

- `len(suggestions) > 5` → `400`；
- 字段类型 / 必填缺失 → `400`。

---

## 通用响应体

本文档内 5 个接口共用下列响应体。

**成功**

```json
{
  "code": 0,
  "msg": "ok"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | `int` | `0` 表示成功 |
| `msg` | `string` | debug |

**失败**

```json
{
  "code": 40001,
  "msg": "exceed max suggestions per call (5)"
}
```

| HTTP 状态 | 典型场景 |
|-----------|----------|
| `400` | 参数格式错误；必填字段缺失；单次 `suggestions` 超过 5；`create` 缺少 `content`；`remove` 传入正文字段 |
| `404` | `/skill/suggestion`、`/skill/remove` 指定的 (`category`, `skill_name`) 不存在 |
| `409` | `/skill/create` 指定的 (`category`, `skill_name`) 已存在 |
| `500` | 后端异常 |

---

## 与算法侧工具的对应关系

| HTTP 接口 | 对应 Python 工具 |
|-----------|------------------|
| `POST /skill/suggestion` | `chat.tools.skill_manager.skill_manage(name, action='modify', category=..., suggestions=...)` |
| `POST /skill/create` | `chat.tools.skill_manager.skill_manage(name, action='create', category=..., content=...)` |
| `POST /skill/remove` | `chat.tools.skill_manager.skill_manage(name, action='remove', category=...)` |
| `POST /memory/suggestion` | `chat.tools.memory.memory(target='memory', suggestions=...)` |
| `POST /user_preference/suggestion` | `chat.tools.memory.memory(target='user', suggestions=...)` |

算法侧工具只做入参合法性校验（长度上限、字段完整性、action 与正文字段的互斥关系、skill 存在性）并将 payload 回传给后端，**不在算法进程中维护任何 pending 列表**；真正的入队、人审、合入、删除均由后端负责。

算法侧提供给后端调用的 `/*/generate` 类接口参见《[算法提供给后端的接口](./algorithm_apis.md)》。
