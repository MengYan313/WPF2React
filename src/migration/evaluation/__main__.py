"""分层评测命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.common.logging import get_logger

from .evaluator import MigrationEvaluator, write_evaluation_outputs
from .manifest_builder import build_evaluation_manifest
from .models import EvaluationManifest
from .visual import VisualMigrationEvaluator, write_visual_evaluation_outputs


logger = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="构建并运行 WPF→React 分层迁移评测",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build-manifest",
        help="从 Parser 产物构建待核验的 evaluation manifest",
    )
    build.add_argument("project_id")
    build.add_argument("--outputs", default="outputs")
    build.add_argument("--target-root")
    build.add_argument(
        "--mapping",
        default="rags/mui/wpf_to_mui_mapping.json",
    )
    build.add_argument("--output")

    run = subparsers.add_parser("run", help="运行冻结后的评测清单")
    run.add_argument("manifest")
    run.add_argument("--method-id", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--workspace-root", default=".")
    run.add_argument("--output-dir", required=True)

    visual_run = subparsers.add_parser(
        "visual-run",
        help="用多模态 LLM 评估清单中的人工截图对",
    )
    visual_run.add_argument("manifest")
    visual_run.add_argument("--method-id", required=True)
    visual_run.add_argument("--run-id", required=True)
    visual_run.add_argument("--workspace-root", default=".")
    visual_run.add_argument("--output-dir", required=True)
    visual_run.add_argument(
        "--model-tier",
        choices=("low", "medium", "high"),
        default="low",
        help="默认 low；未被环境变量覆盖时为 GPT-5.6-Luna",
    )
    return parser


def _write_manifest(manifest: EvaluationManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "build-manifest":
        output_path = Path(
            args.output
            or Path(args.outputs) / args.project_id / "evaluation_manifest.json"
        )
        manifest = build_evaluation_manifest(
            args.project_id,
            output_base_dir=args.outputs,
            target_root=args.target_root,
            mapping_path=args.mapping,
        )
        _write_manifest(manifest, output_path)
        logger.info("已生成待核验评测清单: %s", output_path)
        logger.info(
            "页面=%d，组件=%d，调用边=%d；正式实验前必须独立核验并冻结",
            len(manifest.pages),
            len(manifest.components),
            len(manifest.call_edges),
        )
        return 0

    manifest_path = Path(args.manifest)
    manifest = EvaluationManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if args.command == "visual-run":
        if not manifest.visual_pairs:
            logger.error("评测清单没有 visual_pairs，未发起模型调用")
            return 2
        evaluator = VisualMigrationEvaluator(
            manifest,
            workspace_root=args.workspace_root,
            model_tier=args.model_tier,
        )
        report = asyncio.run(
            evaluator.evaluate(method_id=args.method_id, run_id=args.run_id)
        )
        report_path, records_path = write_visual_evaluation_outputs(
            report,
            args.output_dir,
        )
        logger.info("视觉评测完整报告: %s", report_path)
        logger.info("视觉评测逐截图对证据: %s", records_path)
        return 2 if report.summary.evaluator_errors else 0

    evaluator = MigrationEvaluator(
        manifest,
        workspace_root=args.workspace_root,
    )
    report = evaluator.evaluate(method_id=args.method_id, run_id=args.run_id)
    report_path, records_path = write_evaluation_outputs(
        report,
        args.output_dir,
    )
    logger.info("完整报告: %s", report_path)
    logger.info("逐项证据: %s", records_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
