"""合并当前候选、元数据、审核结论和解析摘要，生成正式数据集清单。"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser.io_utils import read_json, write_json


INCLUDED_STATUSES = {"保留", "条件保留"}


def _compact_run(path: Path) -> dict:
    summary = read_json(path)
    source = dict(summary["source"])
    for key in ("cs_paths", "xaml_paths", "csproj_paths"):
        source.pop(key, None)
    return {
        **{key: value for key, value in summary.items() if key != "source"},
        "source": source,
        "summary_path": path.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="results/dataset/candidate-seed.json")
    parser.add_argument(
        "--assessments", default="results/dataset/candidate-assessments.json"
    )
    parser.add_argument(
        "--metadata", default="outputs/dataset-analysis/github-metadata.json"
    )
    parser.add_argument(
        "--analysis-dir", default="outputs/dataset-analysis/current"
    )
    parser.add_argument("--output", default="results/dataset/dataset-manifest.json")
    args = parser.parse_args()

    seed = read_json(args.seed)
    assessments = {
        item["repository"]: item
        for item in read_json(args.assessments)["assessments"]
    }
    metadata = {
        item["repository"]: item
        for item in read_json(args.metadata)["records"]
    }

    candidates = []
    for item in seed["candidates"]:
        repository = item["repository"]
        assessment = assessments[repository]
        if assessment["status"] not in INCLUDED_STATUSES:
            continue
        local_dir = item["local_dir"]
        project_path = Path("repos") / local_dir
        if not project_path.is_dir():
            raise FileNotFoundError(f"正式数据集仓库不存在: {project_path}")

        github = metadata[repository]["github"]
        candidates.append(
            {
                "repository": repository,
                "url": f"https://github.com/{repository}",
                "local_dir": local_dir,
                "target_paths": item["target_paths"],
                "github": {
                    "stars": github.get("stargazers_count", github.get("stars", 0)),
                    "archived": github.get("archived", False),
                    "license": assessment["analysis_license"],
                },
                "technology": assessment["technology"],
                "status": assessment["status"],
                "decision_reasons": assessment["decision_reasons"],
                "known_limitations": assessment["known_limitations"],
                "analysis": _compact_run(
                    Path(args.analysis_dir) / local_dir / "run_summary.json"
                ),
                "clone_command": f"git clone https://github.com/{repository}.git repos/{local_dir}",
            }
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity_contract": {
            "file_id": "带扩展名的仓库相对 POSIX 路径",
            "page_id": "对应 XAML 的仓库相对 POSIX 路径",
            "parsed_output": "cs|xaml/{source-id}.json",
            "control_output": "dependency/controls/{page-id}.json",
            "page_output": "将 page-id 的 .xaml 替换为 .tsx，并保留目录",
        },
        "candidates": candidates,
    }
    write_json(args.output, manifest)
    print(f"数据集清单: {args.output}（{len(candidates)} 个项目）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
