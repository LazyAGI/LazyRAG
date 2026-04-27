# LazyRAG/evo 接口设计（第二轮重构后）

## 1. 资源统一模型

所有业务流程共享同一个 `Task` 结构：

```json
{
  "id": "run_20240115_120000_a1b2c3d4",
  "flow": "run|apply|eval|abtest|dataset_gen|merge|deploy",
  "status": "queued|running|stopping|paused|succeeded|failed_transient|failed_permanent|cancelled|accepted|rejected|merging|merged|deploying|deployed",
  "thread_id": "thr-xxxx",
  "payload": {},
  "artifacts": [],
  "error_code": null,
  "error_kind": null,
  "created_at": 1705310400.0,
  "updated_at": 1705310400.0,
  "terminal_at": null
}
```

## 2. 生命周期状态机

通用状态：
```
queued -(start)-> running -(stop)-> stopping -(ack)-> paused -(continue)-> running -(finish)-> succeeded
                                      -> failed_transient -(continue)-> running
                                      -> failed_permanent
                                      -> cancelled
queued -(cancel)-> cancelled
```

apply/merge/deploy 额外状态：
```
succeeded -(accept)-> accepted -(merge)-> merging -(finish)-> merged -(deploy)-> deploying -(finish)-> deployed
            -(reject)-> rejected
```

## 3. REST 矩阵

所有 flow 统一形态：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/evo/{flow}s` | 创建任务 |
| GET | `/v1/evo/{flow}s` | 列表 |
| GET | `/v1/evo/{flow}s/{id}` | 详情 |
| POST | `/v1/evo/{flow}s/{id}/stop` | 请求停止 |
| POST | `/v1/evo/{flow}s/{id}/continue` | 继续 |
| POST | `/v1/evo/{flow}s/{id}/cancel` | 取消 |
| GET | `/v1/evo/{flow}s/{id}/events` | SSE 事件流（主路径） |
| GET | `/v1/evo/{flow}s/{id}/artifacts/{name}` | 下载产物 |
| POST | `/v1/evo/{flow}s:cancelAll?scope=thread|global` | 批量取消 |
| POST | `/v1/evo/{flow}s:stopAll?scope=thread|global` | 批量停止 |

apply 额外：
| POST | `/v1/evo/applies/{id}/accept?auto_next=true` | 软接受；auto_next=true 自动触发 merge |
| POST | `/v1/evo/applies/{id}/reject` | 拒绝 |

## 4. SSE 事件类型

| event | 说明 |
|-------|------|
| `message` | 普通日志/事件 |
| `terminal` | 任务终态 |
| `error` | 错误事件 |
| `plan_ready` | Agent 计划就绪 |
| `action` | 操作执行结果 |
| `thinking` | Agent 思考过程 |
| `intent.pending_confirm` | Intent 待确认 |
| `intent.confirmed` | Intent 已确认 |
| `intent.cancelled` | Intent 已取消 |
| `intent.materialized` | Intent 已物化 |

## 5. 错误码

| code | http | retryable | 说明 |
|------|------|-----------|------|
| ILLEGAL_TRANSITION | 409 | no | 非法状态迁移 |
| ACTIVE_TASK_EXISTS | 409 | no | 已有活跃任务 |
| TASK_NOT_FOUND | 404 | no | 任务不存在 |
| INVALID_FLOW | 400 | no | 未知 flow |
| NO_REPORT_AVAILABLE | 409 | no | 无可用报告 |
| MERGE_CONFLICT | 409 | no | 合并冲突 |
| DEPLOY_NO_TARGET | 400 | no | 缺少部署目标 |
| INTENT_EXPIRED | 410 | no | Intent 已过期 |
| INTENT_ALREADY_FINAL | 409 | no | Intent 已终态 |
| INTENT_NOT_FOUND | 404 | no | Intent 不存在 |
| VALIDATION_ERROR | 400 | no | 参数校验失败 |
| PATH_TRAVERSAL | 400 | no | 路径穿越攻击 |
| CONFIG_ERROR | 500 | no | 配置错误 |

## 6. 批量操作 scope

- `scope=thread&thread_id=xxx`: 仅取消指定 thread 下的活跃任务
- `scope=global`: 取消所有活跃任务（需 `Authorization: Bearer $EVO_ADMIN_TOKEN`）

## 7. 两阶段 Intent 流程

```
用户消息 -> Planner.draft -> Intent(reply, preview, requires_confirm)
    -> 若 requires_confirm=true: 等待用户 POST /intents/{id}:confirm
    -> 若 requires_confirm=false: 自动 materialize
    -> Planner.materialize -> PlanResult(ops)
    -> OpsExecutor.execute(ops) -> OpResult[]
```

安全等级：
- `safe`: query.*, chat.list, checkpoint.list_pending, checkpoint.respond — 自动确认
- `destructive`: apply.accept, merge.start, deploy.start, chat.retire, *.cancel — 必须确认
- `long_running`: run.start, apply.start, eval.run, abtest.create, dataset_gen.start — 必须确认

## 8. 模块边界

- `api/*`: 仅协议转换 + 路由
- `service/core`: 任务生命周期唯一入口（store, manager, ops_executor, intent_store）
- `service/executors/*`: 薄适配层（不直接操作 status，用 ctx.report_start/update_payload）
- `service/threads/*`: Thread workspace + EventLog + Checkpoint + Tailer + Hub + Router
- `providers/*`: 外部系统适配器（eval, trace, dataset_source, deploy）
- `orchestrator`: NL→Plan 适配层（planner.draft/materialize，capabilities schema + safety）
- `datagen`: 数据集生成 + 评测（独立模块，不依赖 service/core）
