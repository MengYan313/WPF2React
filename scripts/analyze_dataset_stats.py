"""从结构化清单重新计算数据集统计，并生成两份中文报告。"""

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


INCLUDED_STATUSES = {"保留", "条件保留"}


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _run_totals(candidates: list[dict], key: str) -> dict:
    runs = [candidate.get(key) for candidate in candidates]
    runs = [run for run in runs if run]
    cs_sources = sum(run["source"]["cs_files"] for run in runs)
    xml_sources = sum(run["source"]["xml_files"] for run in runs)
    cs_successes = sum(run["parser"]["cs_successes"] for run in runs)
    xml_successes = sum(run["parser"]["xml_successes"] for run in runs)
    return {
        "runs": len(runs),
        "pipeline_successes": sum(bool(run["pipeline_success"]) for run in runs),
        "pipeline_success_rate": _rate(
            sum(bool(run["pipeline_success"]) for run in runs), len(runs)
        ),
        "source_files": cs_sources + xml_sources,
        "parse_successes": cs_successes + xml_successes,
        "file_parse_success_rate": _rate(
            cs_successes + xml_successes, cs_sources + xml_sources
        ),
        "parse_failures": sum(
            run["parser"]["cs_failures"] + run["parser"]["xml_failures"]
            for run in runs
        ),
        "output_collisions": sum(
            run["parser"]["cs_output_collisions"]
            + run["parser"]["xml_output_collisions"]
            for run in runs
        ),
        "pages": sum(run["parser"]["pages"] for run in runs),
        "controls": sum(run["parser"]["controls"] for run in runs),
        "elapsed_seconds": round(sum(run["elapsed_seconds"] for run in runs), 3),
        "failed_steps": dict(
            sorted(Counter(step for run in runs for step in run["failed_steps"]).items())
        ),
    }


def calculate_statistics(manifest: dict) -> dict:
    candidates = manifest["candidates"]
    included = [candidate for candidate in candidates if candidate["status"] in INCLUDED_STATUSES]
    pdf_candidates = [candidate for candidate in candidates if candidate["source"]["from_pdf"]]
    supplement_candidates = [
        candidate for candidate in candidates if not candidate["source"]["from_pdf"]
    ]
    stars = [candidate["github"]["stars"] for candidate in candidates]
    status_distribution = Counter(candidate["status"] for candidate in candidates)
    stack_distribution = Counter(
        stack for candidate in candidates for stack in candidate["technology"]["stack"]
    )
    license_distribution = Counter(
        candidate["github"].get("analysis_license")
        or candidate["github"].get("license_spdx")
        or "未声明"
        for candidate in candidates
    )
    activity_distribution = Counter(
        candidate["github"]["activity_level"] for candidate in candidates
    )

    return {
        "schema_version": 2,
        "generated_at": manifest["generated_at"],
        "candidate_total": len(candidates),
        "pdf_candidate_total": sum(
            candidate["source"]["from_pdf"] for candidate in candidates
        ),
        "supplement_candidate_total": sum(
            not candidate["source"]["from_pdf"] for candidate in candidates
        ),
        "pdf_starred_total": sum(
            candidate["source"]["starred_in_pdf"] for candidate in candidates
        ),
        "status_distribution": dict(sorted(status_distribution.items())),
        "included_total": len(included),
        "stack_distribution": dict(sorted(stack_distribution.items())),
        "license_distribution": dict(sorted(license_distribution.items())),
        "activity_distribution": dict(sorted(activity_distribution.items())),
        "quality": {
            "stars_min": min(stars) if stars else 0,
            "stars_median": statistics.median(stars) if stars else 0,
            "stars_mean": round(statistics.mean(stars), 2) if stars else 0,
            "stars_max": max(stars) if stars else 0,
            "commits_median": statistics.median(
                candidate["github"]["commit_count_at_ref"] for candidate in candidates
            )
            if candidates
            else 0,
        },
        # 补充候选在解析器优化后才按流程搜索，不得混入
        # “优化前/后”因果对比。
        "baseline": _run_totals(pdf_candidates, "baseline"),
        "final": _run_totals(pdf_candidates, "final"),
        "supplement_initial": _run_totals(supplement_candidates, "baseline"),
        "final_all": _run_totals(candidates, "final"),
        "included_dataset": {
            "repositories": [candidate["repository"] for candidate in included],
            "pages": sum(candidate["final"]["parser"]["pages"] for candidate in included),
            "controls": sum(
                candidate["final"]["parser"]["controls"] for candidate in included
            ),
            "source_files": sum(
                candidate["final"]["source"]["cs_files"]
                + candidate["final"]["source"]["xml_files"]
                for candidate in included
            ),
        },
        "unresolved_issue_count": len(manifest.get("unresolved_issues", [])),
        "parser_optimization_count": len(manifest.get("parser_optimizations", [])),
    }


def _table(rows: list[list[object]]) -> str:
    if not rows:
        return ""
    header, *body = rows
    lines = [
        "| " + " | ".join(map(str, header)) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(map(str, row)) + " |" for row in body)
    return "\n".join(lines)


def render_status_report(manifest: dict, stats: dict) -> str:
    candidates = manifest["candidates"]
    quality = stats["quality"]
    final_elapsed = stats["final"]["elapsed_seconds"]
    speedup = (
        stats["baseline"]["elapsed_seconds"] / final_elapsed
        if final_elapsed
        else None
    )
    lines = [
        "# WPF 实验数据集现状统计",
        "",
        f"数据冻结时间：{manifest['generated_at']}。",
        "",
        "本文由结构化清单和统计脚本生成，所有数值均来自固定提交与本地解析摘要。",
        "",
        "## 0. 权限与环境预检",
        "",
        _table(
            [
                ["项目", "结果"],
                ["Git", manifest["preflight"]["git"]],
                ["GitHub CLI", manifest["preflight"]["github_cli"]],
                ["GitHub SSH", manifest["preflight"]["github_ssh_authentication"]],
                ["GitHub API", manifest["preflight"]["github_api_limit"]],
                ["网络与公开克隆", manifest["preflight"]["network_and_public_clone"]],
                ["启动时磁盘空间", manifest["preflight"]["disk_available_at_start"]],
                ["Python", manifest["preflight"]["python_runtime"]],
                ["解析冒烟", manifest["preflight"]["parser_smoke"]],
                ["候选源码执行", manifest["preflight"]["candidate_code_execution"]],
                ["阻塞性权限问题", "无" if not manifest["preflight"]["blocking_permission_issues"] else "；".join(manifest["preflight"]["blocking_permission_issues"])],
            ]
        ),
        "",
        "## 1. 候选与筛选结果",
        "",
        _table(
            [
                ["指标", "数量"],
                ["候选总数", stats["candidate_total"]],
                ["PDF 原始候选", stats["pdf_candidate_total"]],
                ["GitHub 补充候选", stats["supplement_candidate_total"]],
                ["PDF 星标候选", stats["pdf_starred_total"]],
                ["最终纳入（保留 + 条件保留）", stats["included_total"]],
            ]
        ),
        "",
        _table(
            [["状态", "数量"]]
            + [[status, count] for status, count in stats["status_distribution"].items()]
        ),
        "",
        "## 2. 技术栈与质量",
        "",
        _table(
            [["技术栈标签", "候选数"]]
            + [[name, count] for name, count in stats["stack_distribution"].items()]
        ),
        "",
        _table(
            [["活跃度", "候选数"]]
            + [[name, count] for name, count in stats["activity_distribution"].items()]
        ),
        "",
        _table(
            [["许可证", "候选数"]]
            + [[name, count] for name, count in stats["license_distribution"].items()]
        ),
        "",
        (
            f"Star 最小值/中位数/均值/最大值分别为 "
            f"{quality['stars_min']} / {quality['stars_median']} / "
            f"{quality['stars_mean']} / {quality['stars_max']}；"
            f"分析 ref 的提交数中位数为 {quality['commits_median']}。"
        ),
        "",
        "## 3. 解析器优化前后",
        "",
        "下表仅比较 PDF 中的 22 个原始候选；4 个补充候选依流程在优化后搜索，不混入优化前基线。",
        "",
        _table(
            [
                ["指标", "PDF 原始基线", "PDF 原始优化后"],
                [
                    "七阶段成功率",
                    f"{stats['baseline']['pipeline_successes']}/{stats['baseline']['runs']} ({stats['baseline']['pipeline_success_rate']:.2%})",
                    f"{stats['final']['pipeline_successes']}/{stats['final']['runs']} ({stats['final']['pipeline_success_rate']:.2%})",
                ],
                [
                    "文件解析成功率",
                    f"{stats['baseline']['parse_successes']}/{stats['baseline']['source_files']} ({stats['baseline']['file_parse_success_rate']:.2%})",
                    f"{stats['final']['parse_successes']}/{stats['final']['source_files']} ({stats['final']['file_parse_success_rate']:.2%})",
                ],
                ["文件解析失败", stats["baseline"]["parse_failures"], stats["final"]["parse_failures"]],
                ["同名输出覆盖", stats["baseline"]["output_collisions"], stats["final"]["output_collisions"]],
                ["识别页面", stats["baseline"]["pages"], stats["final"]["pages"]],
                ["累计解析时长（秒）", stats["baseline"]["elapsed_seconds"], stats["final"]["elapsed_seconds"]],
            ]
        ),
        "",
        (
            f"补充候选初次解析成功 "
            f"{stats['supplement_initial']['pipeline_successes']}/"
            f"{stats['supplement_initial']['runs']}；全部候选最终成功 "
            f"{stats['final_all']['pipeline_successes']}/{stats['final_all']['runs']}。"
        ),
        (
            f"PDF 原始候选累计耗时缩短为基线的 {speedup:.2f} 倍。"
            if speedup is not None
            else "PDF 原始候选无可用耗时对比。"
        ),
        "",
        "### 解析器调整",
        "",
    ]
    for item in manifest.get("parser_optimizations", []):
        lines.append(
            f"- {item['name']}：{item['motivation']}；影响：{', '.join(item['affected_repositories'])}；回归：{item['regression_result']}"
        )

    included_stats = stats["included_dataset"]
    lines.extend(
        [
            "",
            "## 4. 最终数据集概况",
            "",
            (
                f"正式实验对象为 {stats['included_total']} 个："
                f"保留 {stats['status_distribution'].get('保留', 0)} 个，"
                f"条件保留 {stats['status_distribution'].get('条件保留', 0)} 个。"
            ),
            (
                f"合计覆盖 {included_stats['source_files']} 个 C#/XAML/csproj 输入、"
                f"{included_stats['pages']} 个页面和 "
                f"{included_stats['controls']} 份控件树。"
            ),
            "",
        ]
    )
    dataset_rows = [["仓库", "来源", "状态", "Star", "提交", "页面", "技术栈", "许可证"]]
    for candidate in candidates:
        if candidate["status"] not in INCLUDED_STATUSES:
            continue
        dataset_rows.append(
            [
                candidate["repository"],
                "PDF" if candidate["source"]["from_pdf"] else "补充",
                candidate["status"],
                candidate["github"]["stars"],
                candidate["github"]["commit_count_at_ref"],
                candidate["final"]["parser"]["pages"],
                ", ".join(candidate["technology"]["stack"]),
                candidate["github"].get("analysis_license")
                or candidate["github"].get("license_spdx")
                or "未声明",
            ]
        )
    lines.append(_table(dataset_rows))

    lines.extend(["", "## 5. 补充搜索终止条件", ""])
    search = manifest["supplement_search"]
    lines.append(f"新增 {search['added_count']} 个候选，上限为 {search['limit']}。")
    for query in search["queries"]:
        lines.append(f"- `{query}`")
    lines.append("")
    lines.append(search["termination_reason"])
    lines.extend(["", "### 已考察但未新增", ""])
    for item in search.get("considered_but_rejected", []):
        lines.append(f"- {item['repository']}：{item['reason']}")

    lines.extend(["", "## 6. 未解决问题", ""])
    for issue in manifest.get("unresolved_issues", []):
        lines.append(f"- {issue}")
    lines.append("")
    return "\n".join(lines)


def render_audit_report(manifest: dict) -> str:
    lines = [
        "# WPF 实验数据集逐项目排查记录",
        "",
        f"数据冻结时间：{manifest['generated_at']}。",
        "",
        "每个项目均只进行静态读取和解析，未执行候选仓库脚本、构建或安装命令。",
        "",
    ]
    for index, candidate in enumerate(manifest["candidates"], 1):
        baseline = candidate["baseline"]
        final = candidate["final"]
        github = candidate["github"]
        lines.extend(
            [
                f"## {index}. {candidate['repository']}",
                "",
                _table(
                    [
                        ["字段", "内容"],
                        ["URL", candidate["url"]],
                        ["来源", "PDF" if candidate["source"]["from_pdf"] else "GitHub 补充搜索"],
                        ["PDF 星标", "是" if candidate["source"]["starred_in_pdf"] else "否"],
                        ["分析 ref", candidate["analysis_ref"]],
                        ["固定 commit", candidate["commit_sha"]],
                        ["目标路径", ", ".join(candidate["target_paths"])],
                        ["Star / 提交数", f"{github['stars']} / {github['commit_count_at_ref']}"],
                        ["最后推送 / 活跃度", f"{github['pushed_at']} / {github['activity_level']}"],
                        ["语言 / 许可证", f"{github['analysis_language']} / {github.get('analysis_license') or github.get('license_spdx') or '未声明'}"],
                        ["技术栈", ", ".join(candidate["technology"]["stack"])],
                        ["克隆", candidate["clone"]["result"]],
                        ["克隆策略", candidate["clone"]["strategy"]],
                    ]
                ),
                "",
                "### 基线与复测",
                "",
                _table(
                    [
                        ["指标", "基线", "最终"],
                        ["七阶段成功", baseline["pipeline_success"], final["pipeline_success"]],
                        ["失败阶段", ", ".join(baseline["failed_steps"]) or "无", ", ".join(final["failed_steps"]) or "无"],
                        ["C# 成功/失败", f"{baseline['parser']['cs_successes']}/{baseline['parser']['cs_failures']}", f"{final['parser']['cs_successes']}/{final['parser']['cs_failures']}"],
                        ["XML 成功/失败", f"{baseline['parser']['xml_successes']}/{baseline['parser']['xml_failures']}", f"{final['parser']['xml_successes']}/{final['parser']['xml_failures']}"],
                        ["页面/控件树", f"{baseline['parser']['pages']}/{baseline['parser']['controls']}", f"{final['parser']['pages']}/{final['parser']['controls']}"],
                        ["同名输出覆盖", baseline["parser"]["cs_output_collisions"] + baseline["parser"]["xml_output_collisions"], final["parser"]["cs_output_collisions"] + final["parser"]["xml_output_collisions"]],
                        ["耗时（秒）", baseline["elapsed_seconds"], final["elapsed_seconds"]],
                    ]
                ),
                "",
                f"失败原因：{candidate['failure_analysis'] or '无。'}",
                "",
                f"相关解析器调整：{'; '.join(candidate['parser_adjustments']) or '无。'}",
                "",
                f"最终结论：**{candidate['status']}**。{'；'.join(candidate['decision_reasons'])}",
                "",
                "已知限制：" + ("；".join(candidate["known_limitations"]) or "无。"),
                "",
                "复现命令：",
                "",
                "```bash",
                *candidate["reproduction_commands"],
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="results/dataset/dataset-manifest.json")
    parser.add_argument(
        "--statistics-output", default="results/dataset/dataset-statistics.json"
    )
    parser.add_argument(
        "--status-report", default="docs/research/wpf-experiment-dataset-status.md"
    )
    parser.add_argument(
        "--audit-report", default="docs/research/wpf-experiment-dataset-audit.md"
    )
    args = parser.parse_args()

    manifest = read_json(args.manifest)
    stats = calculate_statistics(manifest)
    write_json(args.statistics_output, stats)

    status_path = Path(args.status_report)
    audit_path = Path(args.audit_report)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(render_status_report(manifest, stats), encoding="utf-8")
    audit_path.write_text(render_audit_report(manifest), encoding="utf-8")
    print(f"统计 JSON: {args.statistics_output}")
    print(f"现状报告: {status_path}")
    print(f"逐项目报告: {audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
