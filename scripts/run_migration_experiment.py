"""在隔离目录批量运行完整 MigraUI 实验。"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.llm import LLMConfig
from src.migration.baselines.common import (
    copy_parser_outputs,
    create_target_skeleton,
    utc_now,
    write_json,
)
from src.migration.experiment_page_set import load_project_page_selection
from src.migration.migration_orchestrator import MigrationOrchestrator


def _run_directories(
    project: str,
    run_id: str,
    result_base_dir: Path,
    artifact_base_dir: Path,
) -> tuple[Path, Path]:
    for label, value in (("project", project), ("run_id", run_id)):
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError(f"{label} 必须是非空的单段目录名")
    result_root = (result_base_dir / run_id / project).resolve()
    artifact_root = (artifact_base_dir / run_id / project).resolve()
    for path in (result_root, artifact_root):
        if path.exists() and any(path.iterdir()):
            raise FileExistsError(f"实验目录已存在且非空: {path}")
        path.mkdir(parents=True, exist_ok=True)
    return result_root, artifact_root


async def _run_project(
    project: str,
    *,
    run_id: str,
    page_set: Path,
    parser_output_base_dir: Path,
    result_base_dir: Path,
    artifact_base_dir: Path,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    started_at = utc_now()
    started = time.perf_counter()
    result_root, artifact_root = _run_directories(
        project,
        run_id,
        result_base_dir,
        artifact_base_dir,
    )
    skeleton_files = create_target_skeleton(result_root)
    isolated_parser_base = copy_parser_outputs(
        project,
        artifact_root,
        parser_output_base_dir=parser_output_base_dir,
    )
    selection = load_project_page_selection(page_set, project)
    orchestrator = MigrationOrchestrator(
        project_name=project,
        output_base_dir=str(isolated_parser_base),
        result_dir=str(result_root),
        enable_mui_retrieval=True,
        llm_config=llm_config,
    )
    migration = await orchestrator.orchestrate_migration(
        page_names=list(selection.page_ids)
    )
    write_json(artifact_root / "migration_summary.json", migration)
    summary = {
        "method_id": "MigraUI",
        "run_id": run_id,
        "project_id": project,
        "status": "success" if migration["failed_pages"] == 0 else "failed",
        "started_at": started_at,
        "finished_at": utc_now(),
        "wall_time_seconds": round(time.perf_counter() - started, 6),
        "page_set": str(page_set),
        "page_ids": list(selection.page_ids),
        "result_root": str(result_root),
        "artifact_root": str(artifact_root),
        "isolated_parser_output_base": str(isolated_parser_base),
        "model": llm_config.model,
        "total_pages": migration["total_pages"],
        "successful_pages": migration["successful_pages"],
        "failed_pages": migration["failed_pages"],
        "total_components": sum(
            result.get("total_components", 0) for result in migration["results"]
        ),
        "migrated_components": sum(
            result.get("migrated_components", 0) for result in migration["results"]
        ),
        "llm_usage": orchestrator.migration_team.get_llm_usage(),
        "skeleton_files": skeleton_files,
    }
    write_json(artifact_root / "run_manifest.json", summary)
    return summary


async def _main(args: argparse.Namespace) -> int:
    llm_config = LLMConfig.json_mode_config()
    summaries: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, project in enumerate(args.project, 1):
        print(f"[{index}/{len(args.project)}] 迁移 {project}")
        try:
            summaries.append(
                await _run_project(
                    project,
                    run_id=args.run_id,
                    page_set=args.page_set,
                    parser_output_base_dir=args.parser_output_base_dir,
                    result_base_dir=args.result_base_dir,
                    artifact_base_dir=args.artifact_base_dir,
                    llm_config=llm_config,
                )
            )
        except Exception as exc:
            failures.append({"project_id": project, "error": str(exc)})
            print(f"迁移失败: {project}: {exc}", file=sys.stderr)

    index_path = args.artifact_base_dir / args.run_id / "run_index.json"
    write_json(
        index_path,
        {
            "method_id": "MigraUI",
            "run_id": args.run_id,
            "page_set": str(args.page_set),
            "projects": summaries,
            "failures": failures,
        },
    )
    print(f"实验索引: {index_path}")
    return 0 if not failures and all(s["status"] == "success" for s in summaries) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--page-set",
        type=Path,
        default=Path("docs/research/experiment-page-set.json"),
    )
    parser.add_argument(
        "--parser-output-base-dir",
        type=Path,
        default=Path("outputs/parser-completeness/current"),
    )
    parser.add_argument(
        "--result-base-dir",
        type=Path,
        default=Path("results/experiments/MigraUI"),
    )
    parser.add_argument(
        "--artifact-base-dir",
        type=Path,
        default=Path("outputs/experiments/MigraUI"),
    )
    args = parser.parse_args()
    load_dotenv()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
