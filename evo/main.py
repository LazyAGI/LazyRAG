from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from chat.pipelines.builders.get_models import get_automodel

from evo.runtime.config import EvoConfig, load_config


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def default_llm_provider(cfg: EvoConfig) -> Any:
    return lambda: get_automodel(cfg.model_config.llm_role)


def default_embed_provider(cfg: EvoConfig) -> Any:
    return lambda: get_automodel(cfg.model_config.embed_role)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='Evo CLI: run a single diagnosis pipeline locally.',
    )
    p.add_argument('--data-dir', type=Path, default=None)
    p.add_argument('--base-dir', type=Path, default=None,
                   help='Storage base dir (default ./data/evo).')
    p.add_argument('--score-field', default='answer_correctness')
    p.add_argument('--badcase-limit', type=int, default=200)
    p.add_argument('--code-map', type=Path, default=None)
    p.add_argument('--run-id', default=None)
    p.add_argument('--verbose', '-v', action='store_true')
    return p


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


def main() -> int:
    args = build_arg_parser().parse_args(sys.argv[1:])
    setup_logging(args.verbose)
    try:
        config = load_config(
            data_dir=args.data_dir, base_dir=args.base_dir,
            badcase_score_field=args.score_field,
            code_map_path=args.code_map,
        )
        return run_full(config, args)
    except Exception as exc:
        logging.getLogger('evo.main').error('Fatal: %s', exc, exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
