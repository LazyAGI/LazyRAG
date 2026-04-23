# 算法提供给后端的接口 — skill / memory / user_preference 生成

本文档定义**算法侧对业务后端暴露的 HTTP 接口**。算法侧是 server，后端是 client：后端在人审通过后需要将一批 `suggestions` / 用户直接下达的 `user_instruct` 合入已有资源时，调用这些接口由算法生成并返回新的 content。算法侧负责产出结果的**格式合法性**（例如 skill 产出仍然是合法的 SKILL.md、memory / user_preference 产出仍然是可被后续流程消费的文本）。

覆盖三类持久文本资源（skill / memory / user_preference）共 3 个接口：

| 接口 | 用途 |
|------|------|
| `POST /skill/generate` | 依据 `content` + `suggestions` + `user_instruct` 生成新的 SKILL.md 全文 |
| `POST /memory/generate` | 依据入参生成新的 agent memory 全文 |
| `POST /user_preference/generate` | 依据入参生成新的 user_preference 全文 |

> **算法侧是无状态的**：每次请求从 request body 拿齐全部上下文（`content` + `suggestions` + `user_instruct`），不读写算法侧任何持久状态，仅负责生成新内容并保证格式合法。

算法依赖的后端写入接口（`/skill/suggestion`、`/skill/create`、`/skill/remove`、`/memory/suggestion`、`/user_preference/suggestion`）参见《[算法依赖的后端接口](./backend_apis.md)》。

---

## 通用约定

| 项目 | 说明 |
|------|------|
| Method | `POST` |
| Content-Type | `application/json` |
| 鉴权 | 沿用现有会话鉴权方案 |
| `session_id` | **不要求**（生成接口无状态，不绑定会话） |
| `suggestions` | 可选；条目数**不限制**（通常来自 `/suggestion` 累积的全量待审） |
| 错误处理 | 非 2xx 代表请求失败；body 遵循[通用响应体](#通用响应体) |

---

## Suggestion 结构

`suggestions` 列表中的每条目沿用与后端写入接口相同的 `Suggestion` 结构。后端一般从自己累积的待审建议池中挑选后直接透传。

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
| `title` | `string` | 是 | 建议标题 |
| `content` | `string` | 是 | 自然语言描述的修改建议 |
| `reason` | `string` | 否 | 提议理由 |

---

## 通用请求体

三个生成接口共享请求结构，仅 `resource` 语义不同。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | `string` | 是 | 目标资源当前的完整文本。skill 对应 SKILL.md 全文；memory / user_preference 对应相应缓冲区全文 |
| `suggestions` | `Suggestion[]` | 否 | 由后端从已累积的待审建议中挑选后传入。为空或缺省表示本次仅依据 `user_instruct` 生成 |
| `user_instruct` | `string` | 是 | 用户直接下达的修改指令（自然语言） |

---

## 通用响应体

**成功**

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "content": "<生成后的完整文本>"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | `int` | `0` 表示成功 |
| `msg` | `string` | debug |
| `data.content` | `string` | 应用 `suggestions` 与 `user_instruct` 后生成的新内容；算法侧确保其格式合法 |

**失败**

| HTTP 状态 | 典型场景 |
|-----------|----------|
| `400` | 参数格式错误；`content` 或 `user_instruct` 缺失；`suggestions` 条目字段不合法 |
| `422` | 生成产物无法通过格式合法性校验（算法侧重试仍失败后返回） |
| `500` | 后端或模型异常 |

---

## 生成接口

### 1. `POST /skill/generate` — 生成新的 skill content

**Request Body**：参见[通用请求体](#通用请求体)。`content` 为当前 skill 的 SKILL.md 全文。

**请求示例**

```json
{
  "content": "# Git Workflow\n\n## Commit\n- 使用 merge 合并分支\n",
  "suggestions": [
    {
      "title": "补充 rebase 规范",
      "content": "在 Commit 章节加入：团队内优先使用 rebase 保持提交线性。",
      "reason": "近期多次出现 merge commit 污染主干历史"
    }
  ],
  "user_instruct": "再补一条：跨团队协作时才允许使用 merge。"
}
```

**响应**：`data.content` 为新的 SKILL.md 全文，算法侧确保其符合 SKILL.md 的格式约束。

---

### 2. `POST /memory/generate` — 生成新的 memory content

**Request Body**：参见[通用请求体](#通用请求体)。`content` 为当前 agent memory 的全文。

**请求示例**

```json
{
  "content": "- 用户常用编辑器是 VSCode\n- 项目根目录在 ~/workspace\n",
  "suggestions": [
    {
      "title": "记录用户语言偏好",
      "content": "在 memory 中追加一条：该用户偏好用简体中文交流。"
    }
  ],
  "user_instruct": "把过时的编辑器信息删掉，用户现在改用 Cursor 了。"
}
```

**响应**：`data.content` 为新的 memory 全文。

---

### 3. `POST /user_preference/generate` — 生成新的 user_preference content

**Request Body**：参见[通用请求体](#通用请求体)。`content` 为当前用户偏好文本全文。

**请求示例**

```json
{
  "content": "- 响应语言：中文\n",
  "suggestions": [
    {
      "title": "提交前不自动 push",
      "content": "记录用户习惯：在 commit 后不应自动执行 push。"
    }
  ],
  "user_instruct": "保留原有偏好，把新建议合并进去。"
}
```

**响应**：`data.content` 为新的 user_preference 全文。
