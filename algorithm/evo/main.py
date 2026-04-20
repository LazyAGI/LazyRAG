from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from evo.harness.pipeline import RAGAnalysisPipeline
from evo.runtime.config import EvoConfig, load_config
from evo.runtime.session import EmbedProvider, LLMProvider


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def _make_provider(role: str, *, http_timeout: int) -> Any:
    def _provider() -> Any:
        from chat.pipelines.builders.get_models import get_automodel  # type: ignore
        model = get_automodel(role)
        if model is None:
            raise RuntimeError(f'get_automodel({role!r}) returned None.')
        if http_timeout > 0:
            try:
                model._timeout = http_timeout
            except Exception:
                pass
        return model
    return _provider


def default_llm_provider(cfg: EvoConfig) -> LLMProvider:
    return _make_provider('evo_llm', http_timeout=cfg.llm.http_timeout_s)


def default_embed_provider(cfg: EvoConfig) -> EmbedProvider:
    return _make_provider('evo_embed', http_timeout=cfg.embed.http_timeout_s)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='Evo: agent-first RAG analysis system.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''\
Examples:
  python -m evo.main
  python -m evo.main --badcase-limit 200 --score-field faithfulness
  python -m evo.main --code-map /path/to/code_map.json
''',
    )
    p.add_argument('--data-dir', type=Path, default=None)
    p.add_argument('--output-dir', type=Path, default=None)
    p.add_argument('--score-field', default='answer_correctness')
    p.add_argument('--badcase-limit', type=int, default=200)
    p.add_argument('--code-map', type=Path, default=None)
    p.add_argument('--run-id', default=None)
    p.add_argument('--verbose', '-v', action='store_true')
    return p


def run_full(config: EvoConfig, args: argparse.Namespace) -> int:
    log = logging.getLogger('evo.main')
    log.info('Running pipeline (conductor-driven)')
    pipeline = RAGAnalysisPipeline(
        config=config,
        llm_provider=default_llm_provider(config),
        embed_provider=default_embed_provider(config),
    )
    result = pipeline.run(
        badcase_limit=args.badcase_limit,
        run_id=args.run_id,
        score_field=args.score_field,
    )
    log.info('=' * 50)
    if result.success:
        log.info('Done in %.1fs  report=%s', result.elapsed_seconds, result.report_path)
    else:
        for err in result.errors:
            log.error('  %s', err)
    for o in result.outcomes:
        log.info('  %-20s %-8s %.2fs', o.name, o.status, o.elapsed_seconds)
    return 0 if result.success else 1


def main() -> int:
    args = build_arg_parser().parse_args()
    setup_logging(args.verbose)
    try:
        config = load_config(
            data_dir=args.data_dir, output_dir=args.output_dir,
            badcase_score_field=args.score_field,
            code_map_path=args.code_map,
        )
        return run_full(config, args)
    except Exception as exc:
        logging.getLogger('evo.main').error('Fatal: %s', exc, exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
