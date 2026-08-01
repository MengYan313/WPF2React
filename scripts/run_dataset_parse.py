"""运行单个数据集候选的解析流程并保存可复现的结构化摘要。"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser import analyze_project
from src.parser.io_utils import write_json
from src.parser.path_utils import discover_project_files


def _relative_paths(paths: Iterable[Path], root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in paths)


def _duplicate_basenames(paths: Iterable[Path]) -> dict[str, list[str]]:
    paths = list(paths)
    counts = Counter(path.name for path in paths)
    return {
        basename: sorted(str(path) for path in paths if path.name == basename)
        for basename, count in sorted(counts.items())
        if count > 1
    }


def source_inventory(project_path: Path) -> dict:
    all_cs_files = discover_project_files(project_path, [".cs"])
    cs_files = [
        path
        for path in all_cs_files
        if not path.name.endswith(".Designer.cs")
        and path.name != "AssemblyInfo.cs"
    ]
    xaml_files = discover_project_files(project_path, [".xaml"])
    csproj_files = discover_project_files(project_path, [".csproj"])
    xml_files = xaml_files + csproj_files

    return {
        "cs_files": len(cs_files),
        "xaml_files": len(xaml_files),
        "csproj_files": len(csproj_files),
        "xml_files": len(xml_files),
        "cs_duplicate_basenames": _duplicate_basenames(cs_files),
        "xml_duplicate_basenames": _duplicate_basenames(xml_files),
        "cs_paths": _relative_paths(cs_files, project_path),
        "xaml_paths": _relative_paths(xaml_files, project_path),
        "csproj_paths": _relative_paths(csproj_files, project_path),
    }


def summarize_results(results: dict, inventory: dict, elapsed_seconds: float) -> dict:
    steps = results.get("steps", {})
    cs_results = steps.get("cs_parser", {}).get("results", {})
    xaml_results = steps.get("xaml_parser", {}).get("results", {})
    cs_output_paths = list(cs_results.values())
    xaml_output_paths = list(xaml_results.values())
    failed_steps = sorted(
        name for name, result in steps.items() if not result.get("success", False)
    )

    return {
        "elapsed_seconds": round(elapsed_seconds, 3),
        "pipeline_success": len(steps) == 7 and not failed_steps,
        "failed_steps": failed_steps,
        "source": inventory,
        "parser": {
            "cs_successes": len(cs_results),
            "cs_failures": inventory["cs_files"] - len(cs_results),
            "cs_unique_outputs": len(set(cs_output_paths)),
            "cs_output_collisions": len(cs_output_paths) - len(set(cs_output_paths)),
            "xml_successes": len(xaml_results),
            "xml_failures": inventory["xml_files"] - len(xaml_results),
            "xml_unique_outputs": len(set(xaml_output_paths)),
            "xml_output_collisions": len(xaml_output_paths) - len(set(xaml_output_paths)),
            "pages": steps.get("page_dependency", {}).get("total_pages", 0),
            "controls": steps.get("control_dependency", {}).get("files_analyzed", 0),
            "resources": steps.get("resource_dependency", {}).get("total_resources", 0),
        },
        "steps": {
            name: {
                key: value
                for key, value in result.items()
                if key not in {"results", "migration_order"}
            }
            for name, result in steps.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="repos/ 下的候选仓库目录名")
    parser.add_argument(
        "--output-base-dir",
        default="outputs/dataset-analysis/current",
        help="本次解析的输出根目录",
    )
    args = parser.parse_args()

    project_path = Path("repos") / args.project
    if not project_path.is_dir():
        parser.error(f"候选仓库不存在: {project_path}")

    inventory = source_inventory(project_path)
    started = time.monotonic()
    results = analyze_project(args.project, output_base_dir=args.output_base_dir)
    elapsed_seconds = time.monotonic() - started

    summary = {
        "project": args.project,
        "project_path": str(project_path),
        "reproduction_command": (
            f".venv/bin/python scripts/run_dataset_parse.py {args.project} "
            f"--output-base-dir {args.output_base_dir}"
        ),
        **summarize_results(results, inventory, elapsed_seconds),
    }

    summary_path = Path(args.output_base_dir) / args.project / "run_summary.json"
    write_json(summary_path, summary)
    print(f"数据集解析摘要: {summary_path}")
    return 0 if summary["pipeline_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
