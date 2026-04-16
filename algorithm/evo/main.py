"""CLI entry for Evo.  Run: python -m evo.main --help"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from evo.runtime.config import load_config, EvoConfig
from evo.orchestrator.pipeline import RAGAnalysisPipeline, PipelineResult


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Evo: agent-first RAG analysis system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python -m evo.main --full
  python -m evo.main --full --badcase-limit 200 --score-field faithfulness
  python -m evo.main --interactive
""",
    )
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--score-field", default="answer_correctness")
    p.add_argument("--badcase-limit", type=int, default=200)
    p.add_argument("--code-map", type=Path, default='/Users/chenhao7/LocalScripts/LazyRAG/code_map.json')
    p.add_argument("--baseline", type=Path, default=None)
    p.add_argument("--kb-dir", type=Path, default=None)
    p.add_argument("--role", choices=["developer", "ops", "product"], default="developer")
    p.add_argument("--run-id", default=None)
    p.add_argument("--verbose", "-v", action="store_true")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--full", action="store_true", help="Run full pipeline")
    mode.add_argument("--interactive", action="store_true", help="Interactive mode")
    return p


def run_full(config: EvoConfig, args: argparse.Namespace) -> int:
    log = logging.getLogger("evo.main")
    log.info("Running FULL pipeline (agent-first V2)")
    result = RAGAnalysisPipeline(config=config).run(
        badcase_limit=args.badcase_limit, run_id=args.run_id,
        score_field=args.score_field,
        baseline_report_path=getattr(args, "baseline", None),
        role_perspective=args.role,
    )
    log.info("=" * 50)
    if result.success:
        log.info("Done in %.1fs  report=%s", result.elapsed_seconds, result.report_path)
    else:
        for e in result.errors:
            log.error("  %s", e)
    return 0 if result.success else 1


def run_interactive(config: EvoConfig) -> int:
    from evo.tools import register_all
    register_all()
    from evo.agents.base import BaseAnalysisAgent
    from evo.runtime.session import create_session, session_scope

    s = create_session(config=config)
    s.load_judge()
    s.load_trace()
    agent = BaseAnalysisAgent(name="interactive", tool_names=[
        "export_case_evidence", "list_cases_ranked", "summarize_metrics",
        "get_case_detail", "list_code_map", "read_source_file",
        "cluster_badcases", "get_cluster_summary", "list_cluster_exemplars",
    ])
    print("\nEvo Interactive (type 'quit' to exit)\n")
    with session_scope(s):
        while True:
            try:
                q = input("evo> ").strip()
                if not q:
                    continue
                if q.lower() in ("quit", "exit", "q"):
                    break
                print(agent.analyze(q))
            except (KeyboardInterrupt, EOFError):
                break
    return 0


def main() -> int:
    args = build_arg_parser().parse_args()
    setup_logging(args.verbose)
    try:
        extra: dict[str, Any] = {}
        if args.kb_dir:
            extra["kb_dir"] = str(args.kb_dir)
        config = load_config(
            data_dir=args.data_dir, output_dir=args.output_dir,
            model_name=args.model, badcase_score_field=args.score_field,
            code_map_path=args.code_map, extra=extra or None,
        )
        if args.full:
            return run_full(config, args)
        if args.interactive:
            return run_interactive(config)
        return 1
    except Exception as e:
        logging.getLogger("evo.main").error("Fatal: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
