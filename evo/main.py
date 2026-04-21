from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from chat.pipelines.builders.get_models import get_automodel  # type: ignore
from evo.runtime.config import EvoConfig, load_config


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def _make_provider(role: str, *, http_timeout: int) -> Any:
    def _provider() -> Any:
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


def default_llm_provider(cfg: EvoConfig) -> Any:
    return _make_provider('evo_llm', http_timeout=cfg.llm.http_timeout_s)


def default_embed_provider(cfg: EvoConfig) -> Any:
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
  python -m evo.main apply /path/to/report.json --repo /path/to/repo --code-map /path/to/code_map.json
  python -m evo.main apply-resume /path/to/output/apply/<apply_id>
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
    from evo.harness.pipeline import RAGAnalysisPipeline
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


def _build_apply_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='evo apply',
                                description='Apply a diagnosis report via opencode and run tests.')
    p.add_argument('report_json', type=Path, help='Path to the diagnosis report JSON.')
    p.add_argument('--repo', type=Path, default=None,
                   help='Repository root (defaults to current working directory).')
    p.add_argument('--chat-relpath', default='algorithm/chat',
                   help='Path to the chat package, relative to repo root.')
    p.add_argument('--max-rounds', type=int, default=3)
    p.add_argument('--instruction', default='根据 report 完成代码修改')
    p.add_argument('--test-command', default=None,
                   help='Override test command (shell-style string).')
    p.add_argument('--code-map', type=Path, default=None)
    p.add_argument('--output-dir', type=Path, default=None)
    p.add_argument('--model', default=None)
    p.add_argument('--agent', default=None)
    p.add_argument('--variant', default=None)
    p.add_argument('--binary', default=None)
    p.add_argument('--timeout-s', type=int, default=600)
    p.add_argument('--verbose', '-v', action='store_true')
    return p


def _build_apply_resume_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='evo apply-resume',
                                description='Resume an interrupted or failed apply run.')
    p.add_argument('apply_dir', type=Path)
    p.add_argument('--max-rounds', type=int, default=None)
    p.add_argument('--test-command', default=None)
    p.add_argument('--instruction', default=None)
    p.add_argument('--model', default=None)
    p.add_argument('--agent', default=None)
    p.add_argument('--variant', default=None)
    p.add_argument('--binary', default=None)
    p.add_argument('--timeout-s', type=int, default=None)
    p.add_argument('--verbose', '-v', action='store_true')
    return p


def _cmd_apply(argv: Sequence[str]) -> int:
    args = _build_apply_arg_parser().parse_args(list(argv))
    setup_logging(args.verbose)
    from evo.apply import run_apply
    from evo.apply.errors import ApplyError
    from evo.apply.opencode import OpencodeOptions
    import shlex

    try:
        config = load_config(output_dir=args.output_dir, code_map_path=args.code_map)
        options = OpencodeOptions(
            binary=args.binary, model=args.model, agent=args.agent,
            variant=args.variant, timeout_s=args.timeout_s,
        )
        test_command = (tuple(shlex.split(args.test_command))
                        if args.test_command else ('bash', 'tests/run-all.sh'))
        result = run_apply(
            args.report_json, config=config, repo_root=args.repo,
            chat_relpath=args.chat_relpath, max_rounds=args.max_rounds,
            test_command=test_command, instruction=args.instruction,
            opencode_options=options,
        )
    except ApplyError as exc:
        print(json.dumps({'status': 'FAILED', 'error': exc.to_payload()},
                         ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status == 'SUCCEEDED' else 1


def _cmd_apply_resume(argv: Sequence[str]) -> int:
    args = _build_apply_resume_arg_parser().parse_args(list(argv))
    setup_logging(args.verbose)
    from evo.apply import resume_apply
    from evo.apply.errors import ApplyError
    from evo.apply.opencode import OpencodeOptions
    import shlex

    options: OpencodeOptions | None = None
    if any(v is not None for v in
           (args.binary, args.model, args.agent, args.variant, args.timeout_s)):
        options = OpencodeOptions(
            binary=args.binary, model=args.model, agent=args.agent,
            variant=args.variant, timeout_s=args.timeout_s or 600,
        )
    test_command = tuple(shlex.split(args.test_command)) if args.test_command else None

    try:
        result = resume_apply(
            args.apply_dir, max_rounds=args.max_rounds,
            test_command=test_command, instruction=args.instruction,
            opencode_options=options,
        )
    except ApplyError as exc:
        print(json.dumps({'status': 'FAILED', 'error': exc.to_payload()},
                         ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status == 'SUCCEEDED' else 1


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == 'apply':
        return _cmd_apply(argv[1:])
    if argv and argv[0] == 'apply-resume':
        return _cmd_apply_resume(argv[1:])

    args = build_arg_parser().parse_args(argv)
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
