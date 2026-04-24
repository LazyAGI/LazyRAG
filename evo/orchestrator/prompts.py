from __future__ import annotations

from typing import Iterable

from . import capabilities as caps

SYSTEM_PROMPT = """\
你是 evo 的对话编排者。每轮回复**必须**严格按这两段输出:
<ops>
JSON 数组,每项 {"op": "...", "args": {...}, "rationale": "..."} 。
当不需要执行任何动作时输出 [] 。
</ops>
<answer>
给用户的中文回复。
</answer>

只能使用下方列出的 op,严禁编造其他 op。op 之间存在依赖时按数组顺序执行,
失败一条立即停止。stop=暂停可续跑;cancel=放弃不可续。
如果你是带推理能力的模型,推理放在 <think>...</think> 中,evo 会自动捕获。
""".rstrip()


FEW_SHOTS: list[tuple[str, str]] = [
    (
        '启动一次诊断分析,先看 200 条 badcase。',
        '<ops>[{"op":"run.start","args":{},"rationale":"诊断"}]</ops>\n'
        '<answer>已启动分析任务。</answer>',
    ),
    (
        '停掉,直接拿 eval-9b21 跟 apply-c34d 做 abtest。',
        '<ops>[{"op":"run.stop","args":{"task_id":"run-7af3"},"rationale":"暂停分析"},'
        '{"op":"abtest.create","args":{"apply_id":"apply-c34d","baseline_eval_id":"eval-9b21","dataset_id":"ds-default"},"rationale":"对比"}]</ops>\n'
        '<answer>已暂停分析并触发 abtest。</answer>',
    ),
    (
        '当前有哪些 chat 实例?',
        '<ops>[{"op":"chat.list","args":{},"rationale":"列出"}]</ops>\n'
        '<answer>正在查询当前 chat 池。</answer>',
    ),
    (
        '帮我把 chat 部署到 k8s 集群。',
        '<ops>[]</ops>\n'
        '<answer>抱歉,本期 capability 不包含 k8s 部署,'
        '可以考虑 chat.promote 把候选实例升为生产,或者由人工接入。</answer>',
    ),
]


def build_prompt(*, user_message: str,
                 thread_state: str = '',
                 history: Iterable[tuple[str, str]] = ()) -> str:
    parts: list[str] = [SYSTEM_PROMPT, '', caps.render_for_prompt(), '']
    if thread_state:
        parts += ['# Thread state', thread_state, '']
    parts.append('# Few-shot examples')
    for u, a in FEW_SHOTS:
        parts += [f'## user', u, '## assistant', a, '']
    if history:
        parts.append('# Recent dialog')
        for role, content in history:
            parts += [f'## {role}', content, '']
    parts += ['# user', user_message, '', '# assistant']
    return '\n'.join(parts)
