from __future__ import annotations

INDEXER: dict = {
    "type": "object",
    "required": ["hypotheses"],
    "properties": {
        "hypotheses": {"type": "array"},
        "cross_step_narrative": {"type": "string"},
        "open_questions": {"type": "array"},
    },
}

RESEARCHER: dict = {
    "type": "object",
    "required": ["verdict", "refined_claim"],
    "properties": {
        "hypothesis_id": {"type": "string"},
        "verdict": {"type": "string", "minLength": 1},
        "confidence": {"type": "number"},
        "refined_claim": {"type": "string", "minLength": 1},
        "evidence_handles": {"type": "array"},
        "suggested_action": {"type": "string"},
        "reasoning": {"type": "string"},
    },
}

CRITIC: dict = {
    "type": "object",
    "required": ["verdict"],
    "properties": {
        "verdict": {"type": "string", "minLength": 1},
        "approved_confidence": {"type": ["number", "null"]},
        "challenges": {"type": "array"},
    },
}

SYNTHESIZER: dict = {
    "type": "object",
    "required": ["summary", "actions"],
    "properties": {
        "summary": {"type": "string", "minLength": 1},
        "guidance": {"type": "string"},
        "actions": {"type": "array"},
        "open_gaps": {"type": "array"},
        "gap_hypotheses": {"type": "array"},
    },
}

CONDUCTOR: dict = {
    "type": "object",
    "required": ["actions", "done"],
    "properties": {
        "actions": {"type": "array"},
        "done": {"type": "boolean"},
        "rationale": {"type": "string"},
    },
}

ACTION_VERIFIER: dict = {
    "type": "object",
    "required": ["validity_score"],
    "properties": {
        "validity_score": {"type": "number"},
        "supporting_evidence": {"type": "array"},
        "contradicting_evidence": {"type": "array"},
        "notes": {"type": "array"},
    },
}

SCHEMAS: dict[str, dict] = {
    "indexer": INDEXER,
    "researcher": RESEARCHER,
    "critic": CRITIC,
    "synthesizer": SYNTHESIZER,
    "conductor": CONDUCTOR,
    "action_verifier": ACTION_VERIFIER,
}

__all__ = [
    "SCHEMAS",
    "INDEXER",
    "RESEARCHER",
    "CRITIC",
    "SYNTHESIZER",
    "CONDUCTOR",
    "ACTION_VERIFIER",
]
