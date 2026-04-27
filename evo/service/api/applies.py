from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from evo.service.core.manager import JobManager
from evo.service.core.ops_executor import Op, OpsExecutor
from evo.service.core.schemas import ApplyCreate
from evo.service.api.lifecycle import lifecycle_router, _result_to_dict


def build_applies_router(jm: JobManager) -> APIRouter:
    router = lifecycle_router(
        jm,
        flow='apply',
        prefix='/v1/evo/applies',
        create_model=ApplyCreate,
        start_op='apply.start',
        action_ops={'stop': 'apply.stop', 'continue': 'apply.continue',
                    'cancel': 'apply.cancel'},
        get_task_hook=lambda _tid, row: {**row,
                                          'rounds': jm.list_rounds(row['id'])},
    )
    ops = OpsExecutor(jm)

    @router.post('/{apply_id}/accept')
    async def accept_apply(apply_id: str,
                           auto_next: Literal['none', 'merge',
                                              'merge_deploy'] = Query('none')) -> dict:
        result = ops.execute([
            Op('apply.accept',
               {'task_id': apply_id, 'auto_next': auto_next})
        ])[0]
        return _result_to_dict(result)

    @router.post('/{apply_id}/reject')
    async def reject_apply(apply_id: str) -> dict:
        result = ops.execute([Op('apply.reject', {'task_id': apply_id})])[0]
        return _result_to_dict(result)

    return router
