"""将候选种子、GitHub 元数据、解析摘要与人工审核结论合并为数据集清单。"""

from __future__ import annotations

import argparse
import hashlib
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser.io_utils import read_json, write_json


IDENTITY_CHAIN_FILES = [
    "src/common/source_identity.py",
    "src/parser/path_utils.py",
    "src/parser/cs_parser.py",
    "src/parser/xaml_parser.py",
    "src/parser/cs_dependency.py",
    "src/parser/page_dependency.py",
    "src/parser/control_dependency.py",
    "src/parser/indirect_resource_analysis.py",
    "src/parser/resource_dependency.py",
    "src/parser/__main__.py",
    "src/migration/messages.py",
    "src/migration/cs_migrate_agent.py",
    "src/migration/resource_migrate_agent.py",
    "src/migration/page_migrate_agent.py",
    "src/migration/page_assembly_agent.py",
    "src/migration/migration_team.py",
    "src/migration/migration_orchestrator.py",
    "src/migration/baselines/ruletrans.py",
    "src/migration/baselines/llm_direct.py",
    "src/migration/evaluation/manifest_builder.py",
    "src/migration/evaluation/matcher.py",
    "src/migration/evaluation/evaluator.py",
    "src/migration/evaluation/models.py",
    "scripts/run_dataset_parse.py",
]


def _git(project_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(project_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _activity_level(github: dict) -> str:
    if github.get("archived"):
        return "已归档"
    pushed_at = github.get("pushed_at")
    if not pushed_at:
        return "未知"
    pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - pushed).days
    if age_days <= 90:
        return "90 天内活跃"
    if age_days <= 365:
        return "1 年内更新"
    if age_days <= 1095:
        return "3 年内更新"
    return "超过 3 年未更新"


def _compact_run(summary_path: Path) -> dict:
    summary = read_json(summary_path)
    source = dict(summary["source"])
    for key in ["cs_paths", "xaml_paths", "csproj_paths"]:
        source.pop(key, None)
    return {
        **{key: value for key, value in summary.items() if key != "source"},
        "source": source,
        "summary_path": str(summary_path),
    }


def _run_totals(runs: list[dict]) -> dict:
    return {
        "runs": len(runs),
        "pipeline_successes": sum(run["pipeline_success"] for run in runs),
        "elapsed_seconds": round(sum(run["elapsed_seconds"] for run in runs), 3),
        "cs_files": sum(run["source"]["cs_files"] for run in runs),
        "xml_files": sum(run["source"]["xml_files"] for run in runs),
        "cs_failures": sum(run["parser"]["cs_failures"] for run in runs),
        "xml_failures": sum(run["parser"]["xml_failures"] for run in runs),
        "output_collisions": sum(
            run["parser"]["cs_output_collisions"]
            + run["parser"]["xml_output_collisions"]
            for run in runs
        ),
    }


def _reproduction_commands(candidate: dict, commit_sha: str) -> list[str]:
    local_dir = shlex.quote(candidate["local_dir"])
    url = f"https://github.com/{candidate['repository']}.git"
    sparse_paths = " ".join(shlex.quote(path) for path in candidate["target_paths"])
    return [
        f"git clone --filter=blob:none --no-checkout {url} repos/{local_dir}",
        f"git -C repos/{local_dir} fetch --depth 1 origin {commit_sha}",
        f"git -C repos/{local_dir} sparse-checkout set -- {sparse_paths}",
        f"git -C repos/{local_dir} checkout --detach {commit_sha}",
        (
            f".venv/bin/python scripts/run_dataset_parse.py {local_dir} "
            "--output-base-dir outputs/dataset-analysis/final"
        ),
    ]


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
        "--baseline-dir", default="outputs/dataset-analysis/baseline"
    )
    parser.add_argument(
        "--supplement-baseline-dir",
        default="outputs/dataset-analysis/supplement-baseline",
    )
    parser.add_argument("--final-dir", default="outputs/dataset-analysis/final")
    parser.add_argument("--output", default="results/dataset/dataset-manifest.json")
    args = parser.parse_args()

    seed = read_json(args.seed)
    assessments = {
        item["repository"]: item
        for item in read_json(args.assessments)["assessments"]
    }
    metadata_document = read_json(args.metadata)
    metadata = {
        item["repository"]: item for item in metadata_document["records"]
    }
    repositories = {item["repository"] for item in seed["candidates"]}
    if repositories != set(assessments) or repositories != set(metadata):
        raise ValueError("种子、审核结论与元数据的仓库集合不一致")

    candidates = []
    original_baselines = []
    original_finals = []
    for seed_item in seed["candidates"]:
        repository = seed_item["repository"]
        assessment = assessments[repository]
        metadata_item = metadata[repository]
        local_dir = seed_item["local_dir"]
        project_path = Path("repos") / local_dir
        commit_sha = _git(project_path, "rev-parse", "HEAD")
        if commit_sha != metadata_item["commit_sha"]:
            raise ValueError(f"{repository} 本地 commit 与元数据不一致")

        baseline_root = Path(
            args.baseline_dir
            if seed_item["from_pdf"]
            else args.supplement_baseline_dir
        )
        baseline = _compact_run(baseline_root / local_dir / "run_summary.json")
        final = _compact_run(Path(args.final_dir) / local_dir / "run_summary.json")
        if final["commit_sha"] != commit_sha:
            raise ValueError(f"{repository} 最终解析 commit 与本地不一致")
        if seed_item["from_pdf"]:
            original_baselines.append(baseline)
            original_finals.append(final)

        github = dict(metadata_item["github"])
        github.update(
            {
                "analysis_language": github.get("primary_language") or "C#",
                "analysis_license": assessment["analysis_license"],
                "commit_count_at_ref": metadata_item["commit_count_at_ref"],
                "commit_date_at_ref": metadata_item["commit_date"],
                "license_paths": metadata_item["license_paths"],
                "activity_level": _activity_level(github),
            }
        )
        candidates.append(
            {
                "repository": repository,
                "url": f"https://github.com/{repository}",
                "local_dir": local_dir,
                "analysis_ref": seed_item["analysis_ref"],
                "target_paths": seed_item["target_paths"],
                "commit_sha": commit_sha,
                "source": {
                    "from_pdf": seed_item["from_pdf"],
                    "starred_in_pdf": seed_item["starred_in_pdf"],
                    "pdf_note": seed_item["pdf_note"],
                },
                "github": github,
                "technology": assessment["technology"],
                "clone": {
                    "result": "成功；未执行候选仓库脚本或构建命令",
                    "strategy": (
                        "partial clone + sparse-checkout"
                        if _git(project_path, "rev-parse", "--is-shallow-repository") == "true"
                        else "partial clone + sparse-checkout；为确认提交数获取完整历史"
                    ),
                },
                "baseline": baseline,
                "final": final,
                "failure_analysis": assessment["failure_analysis"],
                "parser_adjustments": assessment["parser_adjustments"],
                "status": assessment["status"],
                "decision_reasons": assessment["decision_reasons"],
                "known_limitations": assessment["known_limitations"],
                "decision_evidence": assessment.get("decision_evidence", {}),
                "reproduction_commands": _reproduction_commands(
                    seed_item, commit_sha
                ),
            }
        )

    git_commit = _git(PROJECT_ROOT, "rev-parse", "HEAD")
    cycle_failures = sorted(
        run["project"]
        for run in original_baselines
        if "cs_dependency" in run["failed_steps"]
    )
    original_baseline_totals = _run_totals(original_baselines)
    original_final_totals = _run_totals(original_finals)
    final_all_totals = _run_totals([candidate["final"] for candidate in candidates])
    playnite_baseline = next(
        run for run in original_baselines if run["project"] == "Playnite"
    )
    playnite_final = next(
        run for run in original_finals if run["project"] == "Playnite"
    )
    manifest = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity_contract": {
            "scheme": "repository-relative-posix-v1",
            "file_id": "带扩展名的仓库相对 POSIX 路径",
            "page_id": "对应 XAML 的仓库相对 POSIX 路径",
            "parsed_output": "cs|xaml/{source-id}.json",
            "control_output": "dependency/controls/{page-id}.json",
            "page_output": "将 page-id 的 .xaml 替换为 .tsx，并保留目录",
        },
        "source_pdf": {
            "path": seed["source_pdf"],
            "pages_reviewed": seed["pdf_pages_reviewed"],
            "candidate_count": sum(item["from_pdf"] for item in seed["candidates"]),
        },
        "preflight": {
            "git": "可用",
            "github_cli": "未安装；非阻塞，改用 Git 与公开 GitHub REST API",
            "github_ssh_authentication": "成功",
            "github_api_authenticated": metadata_document.get(
                "authenticated_api", False
            ),
            "github_api_limit": "未认证 core API 60 次/小时；使用本地缓存，最终元数据错误 0",
            "network_and_public_clone": "成功",
            "disk_available_at_start": "约 37 GiB",
            "python_runtime": ".venv/bin/python，Python 3.11",
            "parser_smoke": "ExpenseItDemo 七阶段通过",
            "candidate_code_execution": "未执行候选仓库脚本、构建、测试或安装命令",
            "blocking_permission_issues": [],
        },
        "parser_revision": {
            "baseline_git_commit": git_commit,
            "baseline_worktree_state": "基线开始时工作树无修改",
            "final_git_commit": git_commit,
            "final_worktree_state": "未提交；按用户要求不创建提交",
            "final_source_sha256": {
                path: _sha256(PROJECT_ROOT / path) for path in IDENTITY_CHAIN_FILES
            },
        },
        "baseline_evidence": {
            "original_candidates": original_baseline_totals,
            "original_candidates_final": original_final_totals,
        },
        "parser_optimizations": [
            {
                "name": "可信输入路径发现",
                "motivation": "排除 bin、obj、Generated Files、IDE 和 node_modules 产物，拒绝越界符号链接，并保证顺序确定",
                "affected_repositories": ["Record-Book-App-WPF-MVVM", "Login-In-WPF-MVVM-C-Sharp-and-SQL-Server", "NETworkManager"],
                "regression_result": "离线路径回归通过；Record Book C# 输入从 172 降为 8",
            },
            {
                "name": "C# 历史编码兼容",
                "motivation": "严格 UTF-8 失败时按 Windows-1252/Latin-1 有日志回退",
                "affected_repositories": ["VisualHFT"],
                "regression_result": "VisualHFT C# 失败数从 1 降为 0，编码回归通过",
            },
            {
                "name": "Application 派生根节点识别",
                "motivation": "将 MvxApplication 等自定义 Application 根类型与普通页面分离",
                "affected_repositories": ["MvvmCross"],
                "regression_result": "MvvmCross 页面数从 9 修正为 8，根节点回归通过",
            },
            {
                "name": "C# 引用合并正则索引",
                "motivation": "将逐类型七次扫描改为按类型集合缓存的合并模式",
                "affected_repositories": ["Playnite", "1Remote", "VisualHFT", "ILSpy", "EarTrumpet", "ScreenToGif"],
                "regression_result": f"七种引用语义回归通过；Playnite 总耗时从 {playnite_baseline['elapsed_seconds']} 秒降为 {playnite_final['elapsed_seconds']} 秒",
            },
            {
                "name": "SCC 循环依赖压缩",
                "motivation": "将真实循环依赖压缩后生成确定性拓扑顺序，同时显式记录 cycle_groups",
                "affected_repositories": cycle_failures,
                "regression_result": f"{len(cycle_failures)} 个原始候选由第 3 阶段失败恢复为七阶段通过",
            },
            {
                "name": "多 csproj 资源合并与缺失项目容错",
                "motivation": "合并全部项目文件并按各 csproj 目录验证资源；缺失时输出可审计空结果",
                "affected_repositories": ["Page-Navigation-using-MVVM", "Playnite", "TumblThree", "Accelerider.Windows"],
                "regression_result": "Page Navigation 资源阶段恢复，单/多/缺失 csproj 回归均通过",
            },
            {
                "name": "批量资源引用索引",
                "motivation": "页面与间接资源仅加载一次，所有文件名变体一次扫描建立 Style/Template 反向索引",
                "affected_repositories": ["Playnite", "WPF-Samples", "wpfui", "NETworkManager"],
                "regression_result": "静态资源单/多项目回归通过，Playnite 155 个静态资源可完成分析",
            },
            {
                "name": "仓库相对路径唯一标识",
                "motivation": "用带扩展名的仓库相对 POSIX 路径标识源码和页面，解析、依赖、控件树、迁移、baseline 与评测均镜像目录输出",
                "affected_repositories": ["Accelerider.Windows", "Playnite", "EarTrumpet", "1Remote", "VisualHFT", "ModernFlyouts", "ILSpy", "TumblThree"],
                "regression_result": "26 个候选共 5323 个 C#/XAML/csproj 输入全部解析，输出覆盖由 172 次降为 0；跨目录同名、大小写差异和旧 schema 拒绝回归通过",
            },
            {
                "name": "同名页面依赖消歧与 SCC 调度",
                "motivation": "使用完整 x:Class、当前 namespace 和显式限定名消歧同名窗口，并压缩真实页面循环依赖",
                "affected_repositories": ["Playnite"],
                "regression_result": "Playnite Desktop/Fullscreen 两套同名窗口不再交叉误连；95 个页面生成路径 ID 调度，保留 2 个真实循环组和 2 条未猜测的歧义记录",
            },
        ],
        "supplement_search": {
            "limit": 10,
            "queries": [
                "site:github.com WPF MVVM application stars MIT language:C# GitHub",
                "site:github.com WPF UI gallery MVVM MIT GitHub",
                "topic:wpf language:C# stars:>500 sort:updated",
                "wpf mvvm language:C# stars:>200 sort:updated",
            ],
            "added_count": sum(
                not item["from_pdf"] for item in seed["candidates"]
            ),
            "considered_but_rejected": [
                {"repository": "neelabo/NeeView", "reason": "选定主项目含 2142 个 C# 文件，与已有媒体应用重复且适配成本过高"},
                {"repository": "Kinnara/ModernWpf", "reason": "主体为控件库，与已新增的两个现代 Gallery 重复"},
                {"repository": "Keboo/MaterialDesignInXaml.Examples", "reason": "与 WPF Gallery/Wpf.Ui Gallery 的样式和控件演示覆盖高度重复"},
                {"repository": "AvaloniaUI/Avalonia", "reason": "Avalonia 而非 WPF"},
                {"repository": "abravodev/winforms-mvvm", "reason": "WinForms 而非 WPF"},
            ],
            "termination_reason": "新增 4 个候选已补齐官方 .NET 10 WPF、Fluent 控件 Gallery、现代大型网络工具和中型 MIT 业务应用；后续高排名结果主要是重复的控件库/框架、非 WPF 技术栈或过大且无明显增量价值的媒体应用，因此在 10 个上限前按“无明显补充价值”条件停止。",
        },
        "unresolved_issues": [
            "Playnite 仍有 2 条 MainWindow 短名引用无法仅凭静态 namespace 唯一解析；依赖图明确记录为 ambiguous_references，未建立猜测性边。",
            "本机为 macOS，且候选源码按不可信输入处理；未执行 Windows 构建、候选测试、安装脚本或业务运行时验证。",
            "Page-Navigation-using-MVVM 已淘汰：缺少 .csproj，无法复现原始 WPF 构建，且实际存在的 16 张图片和 2 个字体均未进入资源解析结果。",
            "SnoopLogo 仅条件保留为低复杂度端到端 sanity 样本；缺少复杂 MVVM 业务、数据流和导航场景。",
            "GPL-3.0 与 EarTrumpet 自定义许可的后续分发义务需单独处理；未声明许可的 4 个 PDF 候选已淘汰。",
            "repos/、outputs/ 和 results/ 均为 Git 忽略的本地状态；数据集不再分发他人源码，通过 URL、commit SHA、稀疏路径和复现命令重建。",
        ],
        "candidates": candidates,
    }
    write_json(args.output, manifest)
    print(f"数据集清单: {args.output}，候选 {len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
