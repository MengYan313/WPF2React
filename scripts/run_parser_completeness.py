"""按数据集清单运行阶段一解析器，并保存可复现的全量运行索引。"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_dataset_parse import source_inventory, summarize_results
from src.common.source_identity import SOURCE_ID_SCHEME
from src.parser import analyze_project
from src.parser.io_utils import read_json, write_json


SELECTED_STATUSES = frozenset({"保留", "条件保留"})
DEFAULT_MANIFEST = Path("results/dataset/dataset-manifest.json")
DEFAULT_OUTPUT = Path("outputs/parser-completeness/before")


def _git(project_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(project_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _selected_candidates(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in manifest.get("candidates", [])
        if candidate.get("status") in SELECTED_STATUSES
    ]


def _semantic_file_hashes(project_output: Path) -> dict[str, str]:
    """哈希阶段一结构化产物；运行摘要含耗时，因此不参与语义哈希。"""
    hashes: dict[str, str] = {}
    for path in sorted(project_output.rglob("*.json")):
        if path.name == "run_summary.json":
            continue
        relative = path.relative_to(project_output).as_posix()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _validate_candidate(candidate: dict[str, Any], repos_root: Path) -> dict[str, Any]:
    project_name = str(candidate["local_dir"])
    project_path = repos_root / project_name
    if not project_path.is_dir():
        raise FileNotFoundError(f"本地候选仓库不存在: {project_path}")

    expected_sha = str(candidate["commit_sha"])
    actual_sha = _git(project_path, "rev-parse", "HEAD")
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"{project_name} 固定提交不一致: expected={expected_sha}, actual={actual_sha}"
        )

    missing_targets = [
        target
        for target in candidate.get("target_paths", [])
        if not (project_path / target).exists()
    ]
    if missing_targets:
        raise FileNotFoundError(
            f"{project_name} 缺少清单目标路径: {', '.join(missing_targets)}"
        )

    return {
        "project": project_name,
        "project_path": project_path,
        "expected_commit_sha": expected_sha,
        "actual_commit_sha": actual_sha,
        "worktree_clean": not bool(_git(project_path, "status", "--porcelain")),
    }


def _run_candidate(
    candidate: dict[str, Any],
    *,
    repos_root: Path,
    output_base_dir: Path,
) -> dict[str, Any]:
    preflight = _validate_candidate(candidate, repos_root)
    project_name = preflight["project"]
    inventory = source_inventory(preflight["project_path"])
    started = time.monotonic()
    results = analyze_project(project_name, output_base_dir=str(output_base_dir))
    elapsed_seconds = time.monotonic() - started
    summary = {
        "schema_version": 3,
        "id_scheme": SOURCE_ID_SCHEME,
        "project": project_name,
        "status": candidate["status"],
        "target_paths": list(candidate.get("target_paths", [])),
        "commit_sha": preflight["actual_commit_sha"],
        "worktree_clean": preflight["worktree_clean"],
        "reproduction_command": (
            ".venv/bin/python scripts/run_parser_completeness.py "
            f"--output-base-dir {output_base_dir.as_posix()} --project {project_name} "
            "--allow-existing"
        ),
        **summarize_results(results, inventory, elapsed_seconds),
    }
    project_output = output_base_dir / project_name
    semantic_hashes = _semantic_file_hashes(project_output)
    summary["semantic_artifacts"] = {
        "count": len(semantic_hashes),
        "sha256": semantic_hashes,
    }
    write_json(project_output / "run_summary.json", summary)
    return summary


def _ensure_fresh_namespace(output_base_dir: Path, allow_existing: bool) -> None:
    if not output_base_dir.exists():
        return
    entries = list(output_base_dir.iterdir())
    if entries and not allow_existing:
        raise FileExistsError(
            f"输出命名空间非空，拒绝覆盖历史产物: {output_base_dir}；"
            "请使用新目录，或显式传入 --allow-existing"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repos-root", type=Path, default=Path("repos"))
    parser.add_argument("--output-base-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="仅运行指定 local_dir；可重复传入，默认运行清单中的全部保留项目",
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="允许写入已有命名空间；仍不会删除未涉及的旧文件",
    )
    args = parser.parse_args()

    manifest = read_json(args.manifest)
    candidates = _selected_candidates(manifest)
    if args.project:
        requested = set(args.project)
        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("local_dir") in requested
        ]
        missing = requested - {str(item["local_dir"]) for item in candidates}
        if missing:
            parser.error(f"项目不在当前保留清单中: {', '.join(sorted(missing))}")

    _ensure_fresh_namespace(args.output_base_dir, args.allow_existing)
    args.output_base_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, candidate in enumerate(candidates, start=1):
        project_name = str(candidate["local_dir"])
        print(f"[{index}/{len(candidates)}] 解析 {project_name}")
        try:
            summaries.append(
                _run_candidate(
                    candidate,
                    repos_root=args.repos_root,
                    output_base_dir=args.output_base_dir,
                )
            )
        except Exception as exc:
            failures.append({"project": project_name, "error": str(exc)})
            print(f"解析失败: {project_name}: {exc}", file=sys.stderr)

    run_index = {
        "schema_version": 1,
        "id_scheme": SOURCE_ID_SCHEME,
        "manifest": args.manifest.as_posix(),
        "selected_statuses": sorted(SELECTED_STATUSES),
        "expected_project_count": len(_selected_candidates(manifest)),
        "requested_project_count": len(candidates),
        "completed_project_count": len(summaries),
        "pipeline_success_count": sum(
            1 for summary in summaries if summary["pipeline_success"]
        ),
        "projects": [summary["project"] for summary in summaries],
        "failures": failures,
        "project_summaries": {
            summary["project"]: {
                "commit_sha": summary["commit_sha"],
                "pipeline_success": summary["pipeline_success"],
                "semantic_artifact_count": summary["semantic_artifacts"]["count"],
            }
            for summary in summaries
        },
    }
    write_json(args.output_base_dir / "run_index.json", run_index)
    print(f"全量运行索引: {args.output_base_dir / 'run_index.json'}")
    return 0 if not failures and all(s["pipeline_success"] for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
