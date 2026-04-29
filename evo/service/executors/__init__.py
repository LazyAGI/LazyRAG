from .context import ExecCtx
from . import run, apply, eval_, abtest, dataset_gen

EXECUTORS = {
    'run': run.execute,
    'apply': apply.execute,
    'eval': eval_.execute,
    'abtest': abtest.execute,
    'dataset_gen': dataset_gen.execute,
}

__all__ = ['ExecCtx', 'EXECUTORS', 'run', 'apply', 'eval_', 'abtest',
           'dataset_gen']
