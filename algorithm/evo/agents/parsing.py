"""Shared constants and JSON parsing for perspective agents."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from evo.domain.schemas import PerspectiveHypothesis, PerspectiveReport, InteractionEffect

MAX_EVIDENCE_CHARS = 120_000

_log = logging.getLogger("evo.parsing")

OUTPUT_SCHEMA = """\
You MUST respond with a single JSON object (no markdown fences, no commentary outside the JSON):
{
  "per_step_diagnosis": [
    {
      "step_key": "Retriever_1|ModuleReranker|...",
      "issue": "该步骤的问题描述",
      "severity": "CRITICAL|MEDIUM|LOW|OK",
      "evidence": "支持该判断的证据",
      "suggested_fix": "具体可执行的修复建议"
    }
  ],
  "hypotheses": [
    {
      "stage": "step_key",
      "hypothesis": "为什么这个步骤出现问题",
      "confidence": 0.85,
      "evidence_refs": ["evidence 1", "evidence 2"],
      "reasoning": "推理过程"
    }
  ],
  "interaction_effects": [
    {
      "stages": ["step1", "step2"],
      "description": "上下游交互效应",
      "evidence": "证据"
    }
  ],
  "summary": "总结"
}"""


def cap(text: str) -> str:
    return text[:MAX_EVIDENCE_CHARS] + "\n... (truncated)\n" if len(text) > MAX_EVIDENCE_CHARS else text


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first valid top-level JSON object from arbitrary text.

    Handles: pure JSON, JSON with commentary before/after,
    markdown fences, <think> blocks. Returns None if no valid
    JSON object is found.
    """
    text = _strip_thinking(text)
    # Strip markdown fences
    stripped = text
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
    if stripped.endswith("```"):
        stripped = stripped.rsplit("```", 1)[0]
    stripped = stripped.strip()

    # Fast path: entire text is valid JSON
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Scan for balanced { ... } and try to parse each candidate
    for m in re.finditer(r"\{", stripped):
        start = m.start()
        depth, i = 0, start
        while i < len(stripped):
            if stripped[i] == "{":
                depth += 1
            elif stripped[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(stripped[start : i + 1])
                        if isinstance(candidate, dict):
                            return candidate
                    except json.JSONDecodeError:
                        break
            i += 1
    return None


def parse_perspective_json(raw: str, perspective: str, dataset_ids: list[str]) -> PerspectiveReport:
    data = extract_json_object(raw)
    if data is None:
        _log.warning(
            "parse_perspective_json(%s): JSON extraction failed, raw length=%d, first 200 chars: %s",
            perspective, len(raw), repr(raw[:200]),
        )
        return PerspectiveReport(
            perspective=perspective, dataset_ids=dataset_ids,
            hypotheses=[], summary=_strip_thinking(raw)[:3000],
        )

    _log.info(
        "parse_perspective_json(%s): extracted JSON with %d hypotheses, %d per_step_diagnosis",
        perspective, len(data.get("hypotheses", [])), len(data.get("per_step_diagnosis", [])),
    )

    hyps = [
        PerspectiveHypothesis(
            stage=h.get("stage", "unknown"), hypothesis=h.get("hypothesis", ""),
            confidence=float(h.get("confidence", 0.5)), evidence_refs=h.get("evidence_refs", []),
            counterfactual_checks=h.get("counterfactual_checks", []), reasoning=h.get("reasoning", ""),
        )
        for h in data.get("hypotheses", [])
    ]
    effs = [
        InteractionEffect(stages=e.get("stages", []), description=e.get("description", ""), evidence=e.get("evidence", ""))
        for e in data.get("interaction_effects", [])
    ]
    per_step = data.get("per_step_diagnosis", [])
    return PerspectiveReport(
        perspective=perspective, dataset_ids=dataset_ids, hypotheses=hyps,
        interaction_effects=effs, summary=data.get("summary", ""),
        per_step_diagnosis=per_step,
    )
