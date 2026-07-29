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
DATASET_TAXONOMY_VERSION = 1
DATASET_TAXONOMY = {
    "mvvmlight": {
        "domain": "框架与架构",
        "form": "框架样例",
        "role": "低复杂度 sanity",
        "challenges": ["历史框架", "单页"],
    },
    "MvvmCross": {
        "domain": "框架与架构",
        "form": "框架样例",
        "role": "框架导航专项",
        "challenges": ["MvvmCross 导航", "Playground"],
    },
    "Prism": {
        "domain": "框架与架构",
        "form": "框架样例",
        "role": "框架导航专项",
        "challenges": ["Prism 导航", "模块化", "历史版本"],
    },
    "Login-In-WPF-MVVM-C-Sharp-and-SQL-Server": {
        "domain": "通用业务与交互",
        "form": "业务应用",
        "role": "主业务集",
        "challenges": ["外部数据库", "小样本"],
    },
    "LLPlayer": {
        "domain": "媒体与游戏",
        "form": "业务应用",
        "role": "压力集",
        "challenges": ["自定义控件", "媒体能力", "GPL-3.0"],
    },
    "Accelerider.Windows": {
        "domain": "文件与下载",
        "form": "业务应用",
        "role": "主业务集",
        "challenges": ["Prism 导航", "自定义控件", "页面依赖待核验"],
    },
    "ScreenToGif": {
        "domain": "媒体与游戏",
        "form": "业务应用",
        "role": "压力集",
        "challenges": ["自定义控件", "屏幕捕获", "大规模"],
    },
    "Playnite": {
        "domain": "媒体与游戏",
        "form": "业务应用",
        "role": "压力集",
        "challenges": ["多形态 UI", "主题系统", "大规模"],
    },
    "Flow.Launcher": {
        "domain": "桌面效率与系统集成",
        "form": "业务应用",
        "role": "主业务集",
        "challenges": ["插件架构", "系统集成", "自定义控件"],
    },
    "EarTrumpet": {
        "domain": "桌面效率与系统集成",
        "form": "业务应用",
        "role": "平台专项",
        "challenges": ["Windows 音频", "系统集成", "自定义许可"],
    },
    "1Remote": {
        "domain": "网络与远程管理",
        "form": "业务应用",
        "role": "压力集",
        "challenges": ["远程协议", "高未决依赖", "GPL-3.0"],
    },
    "VisualHFT": {
        "domain": "金融可视化",
        "form": "业务应用",
        "role": "压力集",
        "challenges": ["实时可视化", "插件架构", "高未决依赖"],
    },
    "snoopwpf": {
        "domain": "开发者工具",
        "form": "低复杂度样例",
        "role": "低复杂度 sanity",
        "challenges": ["非业务子项目", "小样本"],
    },
    "OpenGptChat": {
        "domain": "通用业务与交互",
        "form": "业务应用",
        "role": "主业务集",
        "challenges": ["外部 AI API", "小样本"],
    },
    "ModernFlyouts": {
        "domain": "桌面效率与系统集成",
        "form": "业务应用",
        "role": "平台专项",
        "challenges": ["Windows Shell", "已归档", "自定义控件"],
    },
    "ILSpy": {
        "domain": "开发者工具",
        "form": "业务应用",
        "role": "压力集",
        "challenges": ["复杂开发者工具", "历史 WPF 版本", "自定义控件"],
    },
    "WPF-Samples": {
        "domain": "控件与样式 Gallery",
        "form": "控件 Gallery",
        "role": "组件映射专项",
        "challenges": ["Gallery", "业务流程弱", "自定义控件"],
    },
    "wpfui": {
        "domain": "控件与样式 Gallery",
        "form": "控件 Gallery",
        "role": "组件映射专项",
        "challenges": ["Gallery", "第三方控件", "样式密集"],
    },
    "NETworkManager": {
        "domain": "网络与远程管理",
        "form": "业务应用",
        "role": "压力集",
        "challenges": ["大规模", "网络与系统能力", "GPL-3.0"],
    },
    "TumblThree": {
        "domain": "文件与下载",
        "form": "业务应用",
        "role": "主业务集",
        "challenges": ["旧项目格式", "下载队列", "候选依赖多"],
    },
}
PAGE_SCALE_BANDS = (
    (5, "微型（1～5 页）"),
    (19, "小型（6～19 页）"),
    (49, "中型（20～49 页）"),
    (99, "大型（50～99 页）"),
)


def _page_scale(pages: int) -> str:
    for upper, label in PAGE_SCALE_BANDS:
        if pages <= upper:
            return label
    return "超大型（100 页及以上）"


def _included_candidates(manifest: dict) -> list[dict]:
    return [
        candidate
        for candidate in manifest["candidates"]
        if candidate["status"] in INCLUDED_STATUSES
    ]


def _validate_taxonomy(included: list[dict]) -> None:
    projects = {candidate["local_dir"] for candidate in included}
    classified = set(DATASET_TAXONOMY)
    if projects != classified:
        missing = sorted(projects - classified)
        extra = sorted(classified - projects)
        raise ValueError(f"数据集分类与正式项目不一致: missing={missing}, extra={extra}")


def _classification(candidate: dict) -> dict:
    pages = candidate["final"]["parser"]["pages"]
    return {
        **DATASET_TAXONOMY[candidate["local_dir"]],
        "pages": pages,
        "page_scale": _page_scale(pages),
    }


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
    included = _included_candidates(manifest)
    _validate_taxonomy(included)
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
    classifications = [_classification(candidate) for candidate in included]

    return {
        "schema_version": 3,
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
        "taxonomy": {
            "version": DATASET_TAXONOMY_VERSION,
            "projects": {
                candidate["local_dir"]: _classification(candidate)
                for candidate in included
            },
            "domain_distribution": dict(
                sorted(Counter(item["domain"] for item in classifications).items())
            ),
            "form_distribution": dict(
                sorted(Counter(item["form"] for item in classifications).items())
            ),
            "page_scale_distribution": dict(
                sorted(Counter(item["page_scale"] for item in classifications).items())
            ),
            "role_distribution": dict(
                sorted(Counter(item["role"] for item in classifications).items())
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


def render_status_report(
    manifest: dict,
    stats: dict,
    parser_audit: dict | None = None,
    project_rates: dict | None = None,
    determinism: dict | None = None,
) -> str:
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
        "### 1.1 选取方法与合理性",
        "",
        "候选筛选采用“硬约束排除、软证据排序、覆盖增量复核”的三步方法，不以 Star、活跃度或解析成功率中的任一单项替代质量判断。",
        "",
        "硬约束要求候选具有可确认的 WPF/XAML + C# 源码、明确可用的开源许可证、可固定的 commit 和目标路径，以及足以复现工程结构的 `.csproj` 等项目定义。缺少许可证、缺少工程定义、源技术栈不属于 WPF，或源码无法按固定提交重建时直接淘汰。",
        "",
        "通过硬约束后，使用以下软证据判断保留价值：",
        "",
        "- 场景与领域是否补充已有项目，而非重复增加同类小样例；",
        "- 页面规模、MVVM/框架模式、自定义控件、资源和导航机制是否形成难度梯度；",
        "- 官方背景、社区采用、提交历史和近期活跃度是否提供额外质量证据；",
        "- 许可证义务、历史版本、平台绑定和外部服务是否可以被明确记录并在实验中隔离。",
        "",
        "解析七阶段成功只是纳入后的最低可处理性检查，不等同于源码质量、可构建性或迁移正确性。复杂项目不会仅因难迁移而被淘汰，而是进入压力集或平台专项；单页样例、框架 Playground 和 Gallery 也不会与完整业务应用混算一个主指标。",
        "",
        "当前 20 个正式项目曾用于发现并修复解析器问题，因此适合方法开发和分层评测，但不能单独证明对未知仓库的泛化能力。冻结正式实验时还应新增未参与规则开发的外部留出集。",
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

    taxonomy = stats["taxonomy"]
    lines.extend(
        [
            "",
            "## 5. 数据集多轴分类",
            "",
            f"当前分类版本为 {taxonomy['version']}。分类同时记录领域、项目形态、页面规模、迁移挑战和建议实验角色；各轴用途不同，不合并成单一“质量分”。",
            "",
            "逐项目机器可读分类由本脚本写入 `results/dataset/dataset-statistics.json` 的 `taxonomy.projects`，后续抽样脚本应读取该字段，不应复制另一份仓库名单。",
            "",
            "页面规模由阶段一识别的页面 ID 数量确定：微型 1～5 页、小型 6～19 页、中型 20～49 页、大型 50～99 页、超大型 100 页及以上。它只表示实验规模，不等同于迁移难度；自定义控件、框架导航、平台 API、插件架构和外部服务等复杂性由挑战标签单独表达。",
            "",
            _table(
                [["领域", "仓库数"]]
                + [
                    [name, count]
                    for name, count in taxonomy["domain_distribution"].items()
                ]
            ),
            "",
            _table(
                [["项目形态", "仓库数"]]
                + [
                    [name, count]
                    for name, count in taxonomy["form_distribution"].items()
                ]
            ),
            "",
            _table(
                [["页面规模", "仓库数"]]
                + [
                    [name, count]
                    for name, count in taxonomy["page_scale_distribution"].items()
                ]
            ),
            "",
            _table(
                [["建议实验角色", "仓库数"]]
                + [
                    [name, count]
                    for name, count in taxonomy["role_distribution"].items()
                ]
            ),
            "",
        ]
    )
    classification_rows = [
        ["仓库", "领域", "形态", "页面规模", "迁移挑战", "建议实验角色"]
    ]
    for candidate in _included_candidates(manifest):
        item = _classification(candidate)
        classification_rows.append(
            [
                candidate["local_dir"],
                item["domain"],
                item["form"],
                f"{item['page_scale']}；实际 {item['pages']} 页",
                "、".join(item["challenges"]),
                item["role"],
            ]
        )
    lines.append(_table(classification_rows))

    lines.extend(
        [
            "",
            "### 5.1 后续分层实验建议",
            "",
            "- 阶段一完整性实验继续覆盖全部 20 个项目，报告文件、结构、语义引用和资源闭包，不按实验角色删减。",
            "- 主业务集用于比较端到端页面迁移质量；低复杂度 sanity、框架导航、组件映射和平台专项分别报告，不并入同一个业务主指标。",
            "- 压力集按页面规模、根类型、自定义控件比例和未决依赖分层抽样，固定 page ID 与抽样清单；不得只挑选最容易迁移的页面。",
            "- 平台专项只对可迁移的 UI、状态和交互合同评分；Windows 音频、Shell、屏幕捕获和远程协议不得伪装成 React Web 已实现能力。",
            "- 组件映射专项重点测量 WPF/第三方控件到 MUI 的选择和视觉保真，Gallery 的重复控件页面不得主导业务流程指标。",
            "- 每个类别先计算仓库内指标，再对仓库和类别做宏平均；页面数加权的微平均只作为补充，避免 Playnite、NETworkManager 等大型项目淹没小型场景。",
            "- 已知解析缺口涉及的页面或 C# 文件必须先修复，或在冻结 GT 时显式排除并报告；不能把输入缺口归因于迁移模型。",
            "- 正式比较统一冻结仓库 commit、目标路径、数据集分类版本、页面清单、模型、提示词、调用预算和随机种子。",
            "",
            "## 6. 补充搜索终止条件",
            "",
        ]
    )
    search = manifest["supplement_search"]
    lines.append(f"新增 {search['added_count']} 个候选，上限为 {search['limit']}。")
    for query in search["queries"]:
        lines.append(f"- `{query}`")
    lines.append("")
    lines.append(search["termination_reason"])
    lines.extend(["", "### 已考察但未新增", ""])
    for item in search.get("considered_but_rejected", []):
        lines.append(f"- {item['repository']}：{item['reason']}")

    lines.extend(["", "## 7. 未解决问题", ""])
    for issue in manifest.get("unresolved_issues", []):
        lines.append(f"- {issue}")
    lines.append("")
    completeness = render_parser_completeness(
        parser_audit, project_rates, determinism
    )
    if completeness:
        lines.append(completeness)
    return "\n".join(lines)


def render_parser_completeness(
    audit: dict | None,
    project_rates: dict | None,
    determinism: dict | None,
    *,
    section_number: int = 8,
) -> str:
    if not audit:
        return ""

    aggregate = audit["aggregate"]
    files = aggregate["files"]
    xaml = aggregate["xaml"]
    csharp = aggregate["csharp"]
    resources = aggregate["resources"]
    pages = aggregate["pages"]
    rates = aggregate["parser_rates"]
    lines = [
        f"## {section_number}. 阶段一解析完整性",
        "",
        "本节按产物一一对应、结构保留、语义引用显式化和资源闭包审计阶段一结果。解析率中的“已处理”包含显式 unsupported/unresolved，因此它衡量覆盖和可审计性，不是人工 GT 下的语义正确率。",
        "",
        (
            f"- 工程执行：{aggregate['pipeline_success_count']}/"
            f"{audit['expected_project_count']} 个项目七阶段成功。"
        ),
        (
            f"- 文件覆盖：{files['successful_artifacts']}/"
            f"{files['eligible_source_files']} 个 C#/XAML/csproj 输入具有产物；"
            f"缺失 {files['missing_artifacts']}，重复 source ID "
            f"{files['duplicate_source_ids']}，输出覆盖 {files['output_collisions']}。"
        ),
        (
            f"- XAML：{xaml['raw_xml_elements']} 个原始元素全部进入 IR；"
            f"静默未分类 {xaml['silently_unclassified_nodes']}，"
            f"迁移侧视觉差额 {xaml['migration_dropped_visual_nodes']}。"
        ),
        (
            f"- C#：tree-sitter ERROR {csharp['tree_sitter_error_nodes']}，"
            f"missing {csharp['tree_sitter_missing_nodes']}，"
            f"未报告诊断 {csharp['unreported_tree_sitter_diagnostics']}，"
            f"声明差额 {csharp['declaration_gap_total']}。"
        ),
        (
            f"- 资源与页面：解析器未解释资源引用 "
            f"{resources['parser_unexplained_references']}；"
            f"页面迁移顺序 {pages['migration_order_entries']}/{pages['pages']}，"
            f"当前歧义边 {pages['current_unresolved_edges']}。"
        ),
        (
            f"- 七解析器宏平均 {rates['overall']['percentage']:.2f}%，"
            f"阈值 {rates['threshold']:.0%}，"
            f"结论为{'通过' if rates['overall']['passed'] else '未通过'}。"
        ),
        "",
        "### 分解析器解析率",
        "",
        _table(
            [["解析器", "已处理/应处理", "解析率", "结论"]]
            + [
                [
                    parser["label"],
                    f"{parser['handled_units']}/{parser['total_units']}",
                    f"{parser['percentage']:.2f}%",
                    "通过" if parser["passed"] else "未通过",
                ]
                for parser in rates["parsers"].values()
            ]
        ),
        "",
    ]

    if project_rates:
        local_below = []
        for project, summary in project_rates.get("projects", {}).items():
            for parser in summary["parsers"].values():
                if not parser["passed"]:
                    local_below.append(
                        f"{project} 的{parser['label']} {parser['percentage']:.2f}%"
                    )
        if local_below:
            lines.append(
                "更严格的“单项目内每类解析器均达阈值”口径仍有局部低样本项："
                + "；".join(local_below)
                + "。它们不阻塞跨项目聚合验收，但必须在对应类别实验中单独披露。"
            )
            lines.append("")

    if determinism:
        lines.extend(
            [
                (
                    f"两次完整运行比较 {determinism['common_artifact_count']} 个结构化产物，"
                    f"一致 {determinism['matching_artifact_count']} 个；"
                    f"统计报告一致 "
                    f"{determinism['audit_reports']['matching_file_count']}/"
                    f"{determinism['audit_reports']['common_file_count']}，"
                    f"确定性结论为{'通过' if determinism['deterministic'] else '未通过'}。"
                ),
                "",
            ]
        )

    lines.append(
        "完整审计方法、问题聚类和剩余限制见"
        "[阶段一解析完整性两遍式审计](parser-completeness-audit.md)。"
    )
    lines.append("")
    return "\n".join(lines)


def render_audit_report(
    manifest: dict,
    parser_audit: dict | None = None,
    project_rates: dict | None = None,
    determinism: dict | None = None,
) -> str:
    lines = [
        "# WPF 实验数据集逐项目排查记录",
        "",
        f"数据冻结时间：{manifest['generated_at']}。",
        "",
        "每个项目均只进行静态读取和解析，未执行候选仓库脚本、构建或安装命令。",
        "",
        "## 0. 筛选与分类方法",
        "",
        "筛选先执行源技术栈、许可证、固定提交和项目定义等硬约束，再综合领域增量、项目形态、规模梯度、社区与维护证据决定保留或条件保留。Star 和活跃度只作为辅助证据；七阶段成功只证明当前解析器可处理，不证明项目可构建或迁移正确。",
        "",
        "正式项目使用分类版本 1，分别记录领域、项目形态、页面规模、迁移挑战和建议实验角色。页面规模由阶段一页面 ID 数量确定；挑战标签用于记录框架导航、自定义控件、平台 API、插件、外部服务和许可证等不可由页面数表达的因素。复杂项目进入压力集或平台专项，不因难迁移而直接淘汰。",
        "",
        "淘汰条件包括未声明许可证、缺少可复现工程定义、源技术栈不属于 WPF，以及与已有候选高度重复且没有覆盖增量。当前 20 个正式项目参与过解析器问题发现，未来还需使用未参与规则开发的外部留出集验证泛化能力。",
        "",
    ]
    for index, candidate in enumerate(manifest["candidates"], 1):
        baseline = candidate["baseline"]
        final = candidate["final"]
        github = candidate["github"]
        classification_rows = []
        if candidate["status"] in INCLUDED_STATUSES:
            item = _classification(candidate)
            classification_rows = [
                ["领域", item["domain"]],
                ["项目形态", item["form"]],
                ["页面规模", f"{item['page_scale']}；实际 {item['pages']} 页"],
                ["迁移挑战", "、".join(item["challenges"])],
                ["建议实验角色", item["role"]],
            ]
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
                        *classification_rows,
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
    completeness = render_parser_completeness(
        parser_audit,
        project_rates,
        determinism,
        section_number=len(manifest["candidates"]) + 1,
    )
    if completeness:
        lines.append(completeness)
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
    parser.add_argument(
        "--parser-audit-index",
        default="results/parser-completeness/after-run-2/audit-index.json",
    )
    parser.add_argument(
        "--parser-rates",
        default="results/parser-completeness/after-run-2/parser-rates.json",
    )
    parser.add_argument(
        "--determinism-report",
        default="results/parser-completeness/determinism.json",
    )
    args = parser.parse_args()

    manifest = read_json(args.manifest)
    stats = calculate_statistics(manifest)
    write_json(args.statistics_output, stats)
    parser_audit_path = Path(args.parser_audit_index)
    parser_rates_path = Path(args.parser_rates)
    determinism_path = Path(args.determinism_report)
    parser_audit = read_json(parser_audit_path) if parser_audit_path.is_file() else None
    project_rates = (
        read_json(parser_rates_path) if parser_rates_path.is_file() else None
    )
    determinism = read_json(determinism_path) if determinism_path.is_file() else None

    status_path = Path(args.status_report)
    audit_path = Path(args.audit_report)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        render_status_report(
            manifest, stats, parser_audit, project_rates, determinism
        ),
        encoding="utf-8",
    )
    audit_path.write_text(
        render_audit_report(
            manifest, parser_audit, project_rates, determinism
        ),
        encoding="utf-8",
    )
    print(f"统计 JSON: {args.statistics_output}")
    print(f"现状报告: {status_path}")
    print(f"逐项目报告: {audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
