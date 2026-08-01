"""根据当前数据集清单生成统计与简短状态报告。"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser.io_utils import read_json, write_json


def calculate_statistics(manifest: dict) -> dict:
    candidates = manifest["candidates"]
    stars = [candidate["github"]["stars"] for candidate in candidates]
    pages = [candidate["analysis"]["parser"]["pages"] for candidate in candidates]
    controls = [
        candidate["analysis"]["parser"]["controls"] for candidate in candidates
    ]
    source_files = [
        candidate["analysis"]["source"]["cs_files"]
        + candidate["analysis"]["source"]["xml_files"]
        for candidate in candidates
    ]
    return {
        "generated_at": manifest["generated_at"],
        "included_dataset": {
            "repositories": [candidate["repository"] for candidate in candidates],
            "projects": len(candidates),
            "pages": sum(pages),
            "controls": sum(controls),
            "source_files": sum(source_files),
        },
        "status_distribution": dict(
            sorted(Counter(candidate["status"] for candidate in candidates).items())
        ),
        "license_distribution": dict(
            sorted(
                Counter(candidate["github"]["license"] for candidate in candidates).items()
            )
        ),
        "quality": {
            "stars_min": min(stars, default=0),
            "stars_median": statistics.median(stars) if stars else 0,
            "stars_max": max(stars, default=0),
        },
        "projects": {
            candidate["local_dir"]: {
                "repository": candidate["repository"],
                "status": candidate["status"],
                "pages": candidate["analysis"]["parser"]["pages"],
                "controls": candidate["analysis"]["parser"]["controls"],
                "source_files": (
                    candidate["analysis"]["source"]["cs_files"]
                    + candidate["analysis"]["source"]["xml_files"]
                ),
            }
            for candidate in candidates
        },
    }


def render_report(stats: dict) -> str:
    totals = stats["included_dataset"]
    rows = "\n".join(
        f"| {project} | {data['status']} | {data['pages']} | {data['controls']} | {data['source_files']} |"
        for project, data in stats["projects"].items()
    )
    return f"""# WPF 实验数据集现状

当前正式数据集包含 {totals['projects']} 个项目、{totals['pages']} 个页面、{totals['controls']} 个控件和 {totals['source_files']} 个 C#/XAML 输入文件。

| 项目 | 状态 | 页面 | 控件 | 源文件 |
| --- | --- | ---: | ---: | ---: |
{rows}

机器可读清单位于 `results/dataset/dataset-manifest.json`，统计位于 `results/dataset/dataset-statistics.json`。两者只描述当前数据集。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="results/dataset/dataset-manifest.json")
    parser.add_argument(
        "--statistics-output", default="results/dataset/dataset-statistics.json"
    )
    parser.add_argument(
        "--report", default="docs/research/wpf-experiment-dataset-status.md"
    )
    args = parser.parse_args()

    stats = calculate_statistics(read_json(args.manifest))
    write_json(args.statistics_output, stats)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(stats), encoding="utf-8")
    print(f"统计 JSON: {args.statistics_output}")
    print(f"数据集报告: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
