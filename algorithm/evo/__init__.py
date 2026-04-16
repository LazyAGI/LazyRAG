"""Evolution planning utilities for badcase analysis reports."""

__all__ = [
    'TaskPlan',
    'TaskPlannerAgent',
    'build_task_plans',
    'build_lazyllm_task_planner',
    'load_report',
]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(name)
    from . import task_planner_agent
    return getattr(task_planner_agent, name)
