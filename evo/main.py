from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

from evo.runtime.config import EvoConfig, load_config

_ROOT_SUBCOMMANDS = frozenset({'pipeline', 'thread'})
_GLOBAL_ONE_ARG = frozenset({'--data-dir', '--base-dir', '--code-map'})


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def default_llm_provider(cfg: EvoConfig) -> Any:
    from chat.pipelines.builders.get_models import get_automodel
    return lambda: get_automodel(cfg.model_config.llm_role)


def default_embed_provider(cfg: EvoConfig) -> Any:
    from chat.pipelines.builders.get_models import get_automodel
    return lambda: get_automodel(cfg.model_config.embed_role)


def prepend_pipeline_argv(argv: Sequence[str]) -> list[str]:
    av = list(argv)
    if not av:
        return ['pipeline']
    if av[0] in ('-h', '--help'):
        return av
    if av[0] in _ROOT_SUBCOMMANDS:
        return av
    if av[0].startswith('-'):
        i = 0
        while i < len(av):
            t = av[i]
            if t in _GLOBAL_ONE_ARG:
                if i + 1 >= len(av):
                    break
                i += 2
                continue
            if t in ('-v', '--verbose'):
                i += 1
                continue
            break
        if i < len(av) and av[i] in _ROOT_SUBCOMMANDS:
            return av
        return av[:i] + ['pipeline'] + av[i:]
    return av


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Evo CLI: harness pipeline and orchestrator thread flows.',
    )
    parser.add_argument('--data-dir', type=Path, default=None)
    parser.add_argument('--base-dir', type=Path, default=None,
                        help='Storage base dir (default ./data/evo).')
    parser.add_argument('--code-map', type=Path, default=None)
    parser.add_argument('--verbose', '-v', action='store_true')

    sub = parser.add_subparsers(dest='command', required=True)

    pipe = sub.add_parser('pipeline',
                          help='Run conductor diagnosis pipeline (default if args start with -).')
    pipe.add_argument('--score-field', default='answer_correctness')
    pipe.add_argument('--badcase-limit', type=int, default=200)
    pipe.add_argument('--run-id', default=None)

    # New direct flow commands (REST-less CLI)
    eval_p = sub.add_parser('eval', help='Direct eval flow commands.')
    eval_sub = eval_p.add_subparsers(dest='eval_cmd', required=True)
    eval_run_p = eval_sub.add_parser('run', help='Run an evaluation.')
    eval_run_p.add_argument('--dataset-id', required=True)
    eval_run_p.add_argument('--thread-id', default=None)

    ds_p = sub.add_parser('dataset', help='Dataset generation.')
    ds_sub = ds_p.add_subparsers(dest='ds_cmd', required=True)
    ds_gen_p = ds_sub.add_parser('gen', help='Generate dataset from KB.')
    ds_gen_p.add_argument('--kb-id', required=True)
    ds_gen_p.add_argument('--algo-id', default='general_algo')
    ds_gen_p.add_argument('--eval-name', default=None)
    ds_gen_p.add_argument('--thread-id', default=None)

    return parser


def _shared_config_args(ns: argparse.Namespace) -> dict[str, Any]:
    return {
        'data_dir': ns.data_dir,
        'base_dir': ns.base_dir,
        'code_map_path': ns.code_map,
    }


# AutoInputs helper removed in third-wave cleanup (AutoOperator deleted)


def run_full(config: EvoConfig, args: argparse.Namespace) -> int:
    from evo.harness.pipeline import PipelineOptions, build_standard_plan
    from evo.runtime.session import create_session, session_scope
    log = logging.getLogger('evo.main')
    log.info('Running pipeline (conductor-driven)')
    session = create_session(
        config=config, run_id=args.run_id,
        llm_provider=default_llm_provider(config),
        embed_provider=default_embed_provider(config),
    )
    plan = build_standard_plan(
        PipelineOptions(badcase_limit=args.badcase_limit,
                         score_field=args.score_field),
        logger=session.logger('plan'),
    )
    with session_scope(session):
        result = plan.run(session)
    paths = result.get('persist') or {}
    report_path = paths.get('report')
    log.info('=' * 50)
    if result.success:
        log.info('Done in %.1fs  report=%s', result.elapsed_seconds, report_path)
    else:
        for outcome in result.failed:
            log.error('  %s', outcome.error or outcome.name)
    for o in result.outcomes:
        log.info('  %-20s %-8s %.2fs', o.name, o.status, o.elapsed_seconds)
    return 0 if result.success else 1


def main(argv: list[str] | None = None) -> int:
    argv = prepend_pipeline_argv(sys.argv[1:] if argv is None else argv)
    args = build_arg_parser().parse_args(argv)
    setup_logging(args.verbose)
    try:
        if args.command == 'pipeline':
            config = load_config(
                **_shared_config_args(args),
                badcase_score_field=args.score_field,
            )
            return run_full(config, args)
        if args.command == 'eval':
            config = load_config(**_shared_config_args(args))
            from evo.service.core.manager import build_manager
            jm = build_manager(config)
            if args.eval_cmd == 'run':
                tid = jm.submit_eval(
                    thread_id=args.thread_id or '',
                    dataset_id=args.dataset_id)
                print(json.dumps({'eval_id': tid}, ensure_ascii=False))
                return 0
        if args.command == 'dataset':
            config = load_config(**_shared_config_args(args))
            from evo.service.core.manager import build_manager
            jm = build_manager(config)
            if args.ds_cmd == 'gen':
                tid = jm.submit_dataset_gen(
                    thread_id=args.thread_id,
                    kb_id=args.kb_id,
                    algo_id=args.algo_id,
                    eval_name=args.eval_name)
                print(json.dumps({'dataset_id': tid}, ensure_ascii=False))
                return 0
        raise AssertionError(f'unknown command {args.command!r}')
    except Exception as exc:
        logging.getLogger('evo.main').error('Fatal: %s', exc, exc_info=True)
        return 1


# ---- CLI thread commands removed in third-wave cleanup ----
# Thread interaction is now via REST API (Planner + IntentStore + OpsExecutor)
# Old ThreadHub CLI commands (auto/chat/decide) have been deleted.
# Use the API server or direct JobManager calls instead.


if __name__ == '__main__':
    sys.exit(main())
