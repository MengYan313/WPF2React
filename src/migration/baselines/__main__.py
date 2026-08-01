"""命令行入口：python -m src.migration.baselines ..."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from src.migration.experiment_page_set import load_project_page_selection

from .common import METHOD_IDS, METHOD_LLM_DIRECT, METHOD_NO_RAG
from .runner import run_baseline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行可复现的 WPF→React/MUI 实验 baseline",
    )
    parser.add_argument("method_id", choices=METHOD_IDS)
    parser.add_argument("project_id", help="repos/ 下的 WPF 项目目录名")
    parser.add_argument("--run-id", required=True, help="本次运行的唯一标识")
    parser.add_argument("--source-base-dir", default="repos")
    parser.add_argument("--result-base-dir", default="results/baselines")
    parser.add_argument("--artifact-base-dir", default="outputs/baselines")
    parser.add_argument("--parser-output-base-dir", default="outputs")
    parser.add_argument(
        "--page",
        dest="page_names",
        action="append",
        help="只运行指定页面；可重复传入",
    )
    parser.add_argument(
        "--page-set",
        help="从冻结实验页面集合读取当前项目 page ID",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="LLM-Direct-Budget 不执行可选的一次工程合并",
    )
    parser.add_argument(
        "--skip-project-stages",
        action="store_true",
        help="MigraUI-NoRAG 跳过资源/C#/数据阶段，仅用于合成页面 smoke",
    )
    parser.add_argument("--total-token-budget", type=int, default=120_000)
    parser.add_argument("--max-input-tokens-per-call", type=int, default=24_000)
    parser.add_argument("--max-output-tokens-per-call", type=int, default=8_000)
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    if args.no_merge and args.method_id != METHOD_LLM_DIRECT:
        raise ValueError("--no-merge 仅适用于 LLM-Direct-Budget")
    if args.skip_project_stages and args.method_id != METHOD_NO_RAG:
        raise ValueError("--skip-project-stages 仅适用于 MigraUI-NoRAG")
    if args.page_names and args.page_set:
        raise ValueError("--page 与 --page-set 不能同时使用")
    page_names = args.page_names
    if args.page_set:
        page_names = list(
            load_project_page_selection(args.page_set, args.project_id).page_ids
        )
    summary = await run_baseline(
        args.method_id,
        args.project_id,
        args.run_id,
        source_base_dir=args.source_base_dir,
        result_base_dir=args.result_base_dir,
        artifact_base_dir=args.artifact_base_dir,
        parser_output_base_dir=args.parser_output_base_dir,
        page_names=page_names,
        merge_project=not args.no_merge,
        run_project_stages=not args.skip_project_stages,
        total_token_budget=args.total_token_budget,
        max_input_tokens_per_call=args.max_input_tokens_per_call,
        max_output_tokens_per_call=args.max_output_tokens_per_call,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.get("status") == "success" else 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_main_async(args))
    except Exception as exc:
        print(f"baseline 运行失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
