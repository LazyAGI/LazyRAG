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
    """Insert *pipeline* after leading global options so argparse sees parent args first."""
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

    thread = sub.add_parser('thread',
                            help='ThreadHub: auto / interactive chat / single decide().')
    th_sub = thread.add_subparsers(dest='thread_cmd', required=True)

    auto_p = th_sub.add_parser('auto', help='AutoOperator until done or timeout.')
    auto_p.add_argument('--timeout-s', type=float, default=3600.0,
                        help='Seconds before stop_thread + exit 1 (default 3600).')
    auto_p.add_argument('--poll-s', type=float, default=2.0,
                        help='Log cadence while waiting (default 2).')
    auto_p.add_argument('--inputs-json', type=Path, default=None,
                        help='JSON object merged over CLI auto fields.')
    auto_p.add_argument('--badcase-limit', type=int, default=200)
    auto_p.add_argument('--dataset-id', default='ds-default')
    auto_p.add_argument('--baseline-eval-id', default='')
    auto_p.add_argument('--target-chat-url', default='')
    auto_p.add_argument('--on-improvement', default='keep')
    auto_p.add_argument('--on-regression', default='keep')
    auto_p.add_argument('--no-auto-apply', action='store_true',
                        help='Set auto_apply=False')
    auto_p.add_argument('--no-auto-abtest', action='store_true',
                        help='Set auto_abtest=False')

    chat_p = th_sub.add_parser('chat', help='One-shot interactive agent message.')
    chat_p.add_argument('--message', '-m', required=True)
    chat_p.add_argument('--thread-id', default=None,
                        help='Resume existing interactive thread.')

    dec_p = th_sub.add_parser(
        'decide', help='One decide() on new auto thread (no background loop).')
    dec_p.add_argument('--inputs-json', type=Path, default=None)
    dec_p.add_argument('--badcase-limit', type=int, default=200)
    dec_p.add_argument('--dataset-id', default='ds-default')
    dec_p.add_argument('--baseline-eval-id', default='')
    dec_p.add_argument('--target-chat-url', default='')
    dec_p.add_argument('--on-improvement', default='keep')
    dec_p.add_argument('--on-regression', default='keep')
    dec_p.add_argument('--no-auto-apply', action='store_true')
    dec_p.add_argument('--no-auto-abtest', action='store_true')

    return parser


def _shared_config_args(ns: argparse.Namespace) -> dict[str, Any]:
    return {
        'data_dir': ns.data_dir,
        'base_dir': ns.base_dir,
        'code_map_path': ns.code_map,
    }


def _auto_inputs_from_ns(ns: argparse.Namespace) -> dict[str, Any]:
    from evo.orchestrator.auto_operator import AutoInputs

    data: dict[str, Any] = {
        'badcase_limit': ns.badcase_limit,
        'dataset_id': ns.dataset_id,
        'baseline_eval_id': ns.baseline_eval_id,
        'target_chat_url': ns.target_chat_url,
        'on_improvement': ns.on_improvement,
        'on_regression': ns.on_regression,
        'auto_apply': not getattr(ns, 'no_auto_apply', False),
        'auto_abtest': not getattr(ns, 'no_auto_abtest', False),
    }
    path = getattr(ns, 'inputs_json', None)
    if path is not None:
        extra = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(extra, dict):
            raise ValueError('--inputs-json must contain a JSON object')
        data.update(extra)
    keys = frozenset(AutoInputs.__dataclass_fields__)
    return {k: v for k, v in data.items() if k in keys}


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
        if args.command == 'thread':
            config = load_config(**_shared_config_args(args))
            from evo.cli_threads import (
                build_thread_hub, run_auto_cli, run_chat_cli, run_decide_cli,
            )
            hub = build_thread_hub(config)
            if args.thread_cmd == 'auto':
                inputs = _auto_inputs_from_ns(args)
                return asyncio.run(run_auto_cli(
                    hub, inputs=inputs,
                    timeout_s=args.timeout_s, poll_s=args.poll_s))
            if args.thread_cmd == 'chat':
                return asyncio.run(run_chat_cli(
                    hub, message=args.message, thread_id=args.thread_id))
            if args.thread_cmd == 'decide':
                inputs = _auto_inputs_from_ns(args)
                return run_decide_cli(hub, inputs=inputs)
        raise AssertionError(f'unknown command {args.command!r}')
    except Exception as exc:
        logging.getLogger('evo.main').error('Fatal: %s', exc, exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
