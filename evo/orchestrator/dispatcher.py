from __future__ import annotations

from dataclasses import asdict
from typing import Callable

from evo.service.thread_workspace import CheckpointStore, EventLog, ThreadWorkspace

from . import capabilities as caps
from .schemas import Op, OpResult


class Dispatcher:
    def __init__(self, *, jm, base_dir, log: EventLog | None = None,
                 thread_id: str | None = None) -> None:
        self.jm = jm
        self.base_dir = base_dir
        self.log = log
        self.thread_id = thread_id

    def dispatch(self, ops: list[Op]) -> list[OpResult]:
        out: list[OpResult] = []
        for op in ops:
            try:
                caps.validate(op.op, op.args)
                self._log('op.start', {'op': op.op, 'args': op.args})
                result = ROUTES[op.op](self, op)
                self._log('op.dispatched',
                          {'op': op.op, 'task_id': result.task_id,
                           'summary': result.summary})
                out.append(result)
            except Exception as exc:
                self._log('op.failed', {'op': op.op, 'error': str(exc)})
                out.append(OpResult(op=op.op, status='failed',
                                    summary=f'{op.op} failed: {exc}',
                                    error=str(exc)))
                break
        return out

    def _log(self, kind: str, payload: dict) -> None:
        if self.log:
            self.log.append('dispatcher', kind, payload)

    def _require_thread(self) -> str:
        if not self.thread_id:
            raise RuntimeError('this op requires thread context')
        return self.thread_id

    def _workspace(self) -> ThreadWorkspace:
        return ThreadWorkspace(self.base_dir, self._require_thread())

    def _checkpoints(self) -> CheckpointStore:
        ws = self._workspace()
        return CheckpointStore(ws, self.log or EventLog(ws.events_path))


def _summary(op: str, **fields) -> str:
    desc = caps.get(op).description
    detail = ' '.join(f'{k}={v}' for k, v in fields.items() if v)
    return f'{desc}({detail})' if detail else desc


def _dispatched(op: Op, *, task_id: str | None = None,
                payload: dict | None = None, **summary_fields) -> OpResult:
    return OpResult(op.op, 'dispatched',
                    _summary(op.op, **summary_fields),
                    task_id=task_id, payload=payload or {})


def _completed(op: Op, *, payload: dict | None = None,
               **summary_fields) -> OpResult:
    return OpResult(op.op, 'completed',
                    _summary(op.op, **summary_fields),
                    payload=payload or {})


# --- handlers ---------------------------------------------------------------

def _h_run_start(d, op):
    return _dispatched(op, task_id=d.jm.submit_run(
        thread_id=d.thread_id,
        eval_id=op.args.get('eval_id'),
        badcase_limit=op.args.get('badcase_limit'),
        score_field=op.args.get('score_field')))


def _h_apply_start(d, op):
    return _dispatched(op, task_id=d.jm.submit_apply(
        report_id=op.args.get('report_id'), thread_id=d.thread_id))


def _h_eval_fetch(d, op):
    tid = d.jm.submit_eval(eval_id=op.args['eval_id'],
                            thread_id=d._require_thread())
    return _dispatched(op, task_id=tid, eval_id=op.args['eval_id'])


def _h_eval_run(d, op):
    tid = d.jm.submit_eval(dataset_id=op.args['dataset_id'],
                            target_chat_url=op.args.get('target_chat_url'),
                            options=op.args.get('options'),
                            thread_id=d._require_thread())
    return _dispatched(op, task_id=tid, dataset_id=op.args['dataset_id'])


def _h_abtest_create(d, op):
    tid = d.jm.submit_abtest(
        thread_id=d._require_thread(),
        apply_id=op.args['apply_id'],
        baseline_eval_id=op.args['baseline_eval_id'],
        dataset_id=op.args['dataset_id'],
    )
    return _dispatched(op, task_id=tid)


def _transition(action: str):
    def handler(d, op):
        tid = op.args['task_id']
        getattr(d.jm, action)(tid)
        return _dispatched(op, task_id=tid)
    return handler


def _h_checkpoint_respond(d, op):
    rec = d._checkpoints().respond(
        op.args['cp_id'], choice=op.args['choice'],
        feedback=op.args.get('feedback'),
        responder=op.args.get('responder', 'user'))
    return _dispatched(op, cp_id=op.args['cp_id'],
                       payload={'status': rec['status']})


def _h_checkpoint_list(d, op):
    return _completed(op, payload={'pending': d._checkpoints().list_pending()})


def _h_chat_list(d, op):
    items = []
    for inst in d.jm.chat_registry.list():
        d_ = asdict(inst)
        d_['source_dir'] = str(d_['source_dir'])
        items.append(d_)
    return _completed(op, payload={'instances': items})


_CHAT_ROLE = {'chat.demote':  {'role': 'candidate'},
              'chat.retire':  {'role': 'retired'},
              'chat.stop':    {'role': 'retired', 'status': 'stopped'}}


def _h_chat_role(d, op):
    cid = op.args['chat_id']
    d.jm.chat_registry.update(cid, **_CHAT_ROLE[op.op])
    return _completed(op, chat_id=cid, payload={'chat_id': cid})


def _h_chat_promote(d, op):
    cid = op.args['chat_id']
    reg = d.jm.chat_registry
    retired = []
    for inst in reg.list(role='production'):
        if inst.chat_id == cid:
            continue
        reg.update(inst.chat_id, role='retired')
        retired.append(inst.chat_id)
    reg.update(cid, role='production')
    return _completed(op, chat_id=cid,
                       payload={'chat_id': cid, 'retired': retired})


def _h_query_list_threads(d, op):
    base = d.base_dir / 'state' / 'threads'
    threads = sorted(p.name for p in base.glob('*') if p.is_dir()) if base.exists() else []
    return _completed(op, payload={'threads': threads})


def _h_query_list_evals(d, op):
    return _completed(op, payload={'evals': sorted(
        p.stem for p in d._workspace().dir.glob('evals/*.json'))})


def _h_query_get_report(d, op):
    rid = op.args['report_id']
    candidate = d.jm.config.storage.reports_dir / f'{rid}.json'
    return _completed(op, report_id=rid,
                      payload={'report_path': str(candidate),
                               'exists': candidate.exists()})


ROUTES: dict[str, Callable[['Dispatcher', Op], OpResult]] = {
    'run.start':     _h_run_start,
    'run.stop':      _transition('stop'),
    'run.continue':  _transition('cont'),
    'run.cancel':    _transition('cancel'),
    'apply.start':   _h_apply_start,
    'apply.stop':    _transition('stop'),
    'apply.continue':_transition('cont'),
    'apply.cancel':  _transition('cancel'),
    'apply.accept':  _transition('accept'),
    'apply.reject':  _transition('reject'),
    'eval.fetch':    _h_eval_fetch,
    'eval.run':      _h_eval_run,
    'eval.cancel':   _transition('cancel'),
    'abtest.create': _h_abtest_create,
    'abtest.stop':   _transition('stop'),
    'abtest.continue':_transition('cont'),
    'abtest.cancel': _transition('cancel'),
    'chat.list':     _h_chat_list,
    'chat.stop':     _h_chat_role,
    'chat.promote':  _h_chat_promote,
    'chat.demote':   _h_chat_role,
    'chat.retire':   _h_chat_role,
    'checkpoint.respond':      _h_checkpoint_respond,
    'checkpoint.list_pending': _h_checkpoint_list,
    'query.list_threads': _h_query_list_threads,
    'query.get_report':   _h_query_get_report,
    'query.list_evals':   _h_query_list_evals,
    'query.list_chats':   _h_chat_list,
}


_missing = set(caps.REGISTRY) ^ set(ROUTES)
assert not _missing, f'capability/handler mismatch: {sorted(_missing)}'
del _missing
