from datetime import datetime

import pytest
from pydantic import ValidationError

from chat.utils.schema import BaseMessage, MiddleResults, PlanStep, SessionMemory, TaskContext


def test_base_message_validates_role_and_rejects_extra_fields():
    msg = BaseMessage(role='user', content='hello', time='2026-04-16T00:00:00Z')

    assert msg.role == 'user'
    assert isinstance(msg.time, datetime)

    with pytest.raises(ValidationError):
        BaseMessage(role='guest', content='hello')
    with pytest.raises(ValidationError):
        BaseMessage(role='user', content='hello', extra='x')


def test_session_memory_and_task_context_defaults_are_isolated():
    memory = SessionMemory()
    ctx1 = TaskContext()
    ctx2 = TaskContext()

    memory.entities.append('alpha')
    ctx1.pending_steps.append(PlanStep(step_id=1, goal='search', tool='kb'))
    ctx1.middle_results.raw_results.append('node-1')

    assert memory.entities == ['alpha']
    assert ctx2.pending_steps == []
    assert ctx2.middle_results == MiddleResults()


def test_plan_step_defaults_to_pending_status():
    step = PlanStep(step_id=3, goal='summarize', tool='generator')

    assert step.status == 'pending'
    assert step.raw_results == []
    assert step.formatted_results == []
