"""从逐项目完整性审计清单生成跨项目问题聚类与前后对比报告。"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser.io_utils import read_json, write_json


DEFAULT_BEFORE = Path("results/parser-completeness/before")
DEFAULT_OUTPUT = Path("results/parser-completeness")
TRACKED_XAML_SEMANTICS = (
    "binding",
    "multibinding",
    "prioritybinding",
    "command",
    "command_parameter",
    "event_handler",
    "static_resource",
    "dynamic_resource",
)


def _reports(root: Path) -> list[dict[str, Any]]:
    return [read_json(path) for path in sorted((root / "projects").glob("*.json"))]


def _affected(
    reports: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]
) -> list[str]:
    return sorted(report["project"] for report in reports if predicate(report))


def _declaration_gaps(reports: list[dict[str, Any]]) -> dict[str, int]:
    raw: Counter[str] = Counter()
    ir: Counter[str] = Counter()
    for report in reports:
        raw.update(report["csharp"]["raw_declarations"])
        ir.update(report["csharp"]["ir_declarations"])
    return {
        kind: max(0, raw[kind] - ir[kind])
        for kind in sorted(set(raw) | set(ir))
        if raw[kind] > ir[kind]
    }


def _semantic_gaps(reports: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    occurrences: Counter[str] = Counter()
    structured: Counter[str] = Counter()
    for report in reports:
        occurrences.update(report["xaml"]["occurrences"])
        structured.update(report["xaml"]["structured_extractions"])
    return {
        kind: {
            "occurrences": occurrences[kind],
            "structured": structured[kind],
            "gap": max(0, occurrences[kind] - structured[kind]),
        }
        for kind in TRACKED_XAML_SEMANTICS
    }


def build_clusters(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    semantic_gaps = _semantic_gaps(reports)
    declaration_gaps = _declaration_gaps(reports)
    clusters = [
        {
            "cluster_id": "file-identity-chain",
            "priority": 1,
            "category": "文件身份与覆盖",
            "motivation": "文件覆盖、错误身份映射或 basename 回退会使后续所有指标失真。",
            "affected_projects": _affected(
                reports,
                lambda r: bool(
                    r["files"]["missing_artifacts"]
                    or r["files"]["duplicate_source_ids"]
                    or r["files"]["output_collisions"]
                ),
            ),
            "before_metrics": {
                "eligible_files": sum(r["files"]["eligible_source_files"] for r in reports),
                "missing_artifacts": sum(r["files"]["missing_artifacts"] for r in reports),
                "duplicate_source_ids": sum(r["files"]["duplicate_source_ids"] for r in reports),
                "output_collisions": sum(r["files"]["output_collisions"] for r in reports),
            },
            "planned_fix": "保持 repository-relative-posix-v1 全链路与镜像输出，并用同名跨目录端到端夹具锁定。",
            "risk": "任何 basename、stem 或类名回退都会重新引入误匹配。",
        },
        {
            "cluster_id": "xaml-migration-node-inventory",
            "priority": 2,
            "category": "XAML 确定结构损失",
            "motivation": "完整 XAML IR 保留了元素，但迁移控件树会删除自定义控件、非基础视觉节点及资源子树。",
            "affected_projects": _affected(
                reports,
                lambda r: bool(r["xaml"].get("migration_dropped_visual_nodes", 0)),
            ),
            "before_metrics": {
                "page_visual_nodes": sum(r["xaml"].get("page_visual_nodes", 0) for r in reports),
                "migration_control_ir_nodes": sum(r["xaml"].get("migration_control_ir_nodes", 0) for r in reports),
                "dropped_visual_nodes": sum(r["xaml"].get("migration_dropped_visual_nodes", 0) for r in reports),
                "page_custom_controls": sum(r["xaml"].get("page_custom_controls", 0) for r in reports),
            },
            "planned_fix": "在不破坏现有基础控件树消费者的前提下，新增完整节点分类清单、原始节点路径、属性与保留/忽略原因。",
            "risk": "直接把全部属性元素塞入旧 controls 会改变迁移遍历语义，应使用独立清单或明确节点角色。",
        },
        {
            "cluster_id": "xaml-semantic-references",
            "priority": 2,
            "category": "XAML 确定语义损失",
            "motivation": "Binding、Command、事件和资源标记当前只存在于原始字符串，后续阶段无法稳定消费或审计。",
            "affected_projects": _affected(
                reports,
                lambda r: any(
                    r["xaml"]["occurrences"].get(kind, 0)
                    > r["xaml"]["structured_extractions"].get(kind, 0)
                    for kind in TRACKED_XAML_SEMANTICS
                ),
            ),
            "before_metrics": semantic_gaps,
            "planned_fix": "在 XAML 节点 IR 上增加确定性的 semantic_references，保存 kind、属性、原值、目标、节点路径和源码行。",
            "risk": "嵌套标记扩展不能用简单逗号切分；无法可靠解析的表达式必须保留 raw_value 并标为 unsupported。",
        },
        {
            "cluster_id": "csharp-declaration-coverage",
            "priority": 2,
            "category": "C# 确定声明损失",
            "motivation": "file-scoped namespace、record、事件字段、多声明字段及部分成员没有完整进入 C# IR。",
            "affected_projects": _affected(
                reports,
                lambda r: any(
                    count > r["csharp"]["ir_declarations"].get(kind, 0)
                    for kind, count in r["csharp"]["raw_declarations"].items()
                ),
            ),
            "before_metrics": {"declaration_gaps": declaration_gaps},
            "planned_fix": "按 tree-sitter 语法节点补齐声明种类和多 declarator，并保留类型参数、泛型类型、修饰符与源码范围。",
            "risk": "不能把语法恢复节点计为完整声明；ERROR 覆盖范围应单独记录。",
        },
        {
            "cluster_id": "tree-sitter-diagnostics",
            "priority": 2,
            "category": "C# 部分解析与诊断",
            "motivation": "阶段成功当前不会暴露 tree-sitter ERROR 或缺失节点，可能把部分解析误当完整。",
            "affected_projects": _affected(
                reports,
                lambda r: bool(
                    r["csharp"]["tree_sitter_error_nodes"]
                    or r["csharp"]["tree_sitter_missing_nodes"]
                ),
            ),
            "before_metrics": {
                "error_nodes": sum(r["csharp"]["tree_sitter_error_nodes"] for r in reports),
                "missing_nodes": sum(r["csharp"]["tree_sitter_missing_nodes"] for r in reports),
            },
            "planned_fix": "把 tree-sitter ERROR/missing 节点、源码范围和证据写入每文件 diagnostics，不因存在诊断而丢弃其余可解析结构。",
            "risk": "ERROR 节点可能来自条件编译或语法版本差异，必须报告而不是武断修复源码。",
        },
        {
            "cluster_id": "partial-type-association",
            "priority": 3,
            "category": "跨文件 C# 类型关联",
            "motivation": "partial 修饰符被保留，但当前依赖产物没有按完整类型名给出部分类型关联文件。",
            "affected_projects": _affected(
                reports, lambda r: bool(r["csharp"]["partial_type_groups"])
            ),
            "before_metrics": {
                "partial_groups": sum(r["csharp"]["partial_type_groups"] for r in reports),
                "partial_files": sum(r["csharp"]["partial_type_files"] for r in reports),
            },
            "planned_fix": "按 namespace + 类型名生成确定性 partial_groups，并保留同名不同命名空间的独立身份。",
            "risk": "仅按简单类型名分组会错误合并不同命名空间。",
        },
        {
            "cluster_id": "resource-closure",
            "priority": 3,
            "category": "资源闭包",
            "motivation": "csproj 声明不是完整资源清单，XAML 直接引用、未声明仓库文件、动态键和缺失目标需要统一分类。",
            "affected_projects": _affected(
                reports,
                lambda r: bool(
                    r["resources"]["repository_resource_files"]
                    > r["resources"]["parser_resource_source_ids"]
                    or r["resources"]["xaml_file_references"]
                    > r["resources"]["parser_linked_references"]
                    or r["resources"]["target_missing"]
                    or r["resources"]["dynamic_or_unsupported_references"]
                ),
            ),
            "before_metrics": {
                "repository_resource_files": sum(r["resources"]["repository_resource_files"] for r in reports),
                "parser_resource_source_ids": sum(r["resources"]["parser_resource_source_ids"] for r in reports),
                "xaml_file_references": sum(r["resources"]["xaml_file_references"] for r in reports),
                "parser_linked_references": sum(r["resources"]["parser_linked_references"] for r in reports),
                "missing_targets": sum(r["resources"]["target_missing"] for r in reports),
                "unexplained_references": sum(r["resources"]["unexplained_references"] for r in reports),
            },
            "planned_fix": "合并全部 csproj 声明、XAML 引用与仓库资源扫描；缺少 csproj 时仍生成带来源和分类的资源清单。",
            "risk": "仓库中的所有图片不一定属于目标 WPF 项目，fallback 必须标注 discovery_source 与声明状态。",
        },
        {
            "cluster_id": "page-navigation-candidates",
            "priority": 3,
            "category": "页面与业务依赖",
            "motivation": "仅识别 new Page() 会遗漏 DataTemplate、Prism、MvvmCross、DI、Command 与字符串路由。",
            "affected_projects": _affected(
                reports,
                lambda r: bool(
                    r["pages"]["audit_navigation_candidates"]
                    or r["pages"]["current_unresolved_edges"]
                ),
            ),
            "before_metrics": {
                "certain_edges": sum(r["pages"]["certain_edges"] for r in reports),
                "audit_candidates": sum(r["pages"]["audit_navigation_candidates"] for r in reports),
                "current_unresolved": sum(r["pages"]["current_unresolved_edges"] for r in reports),
            },
            "planned_fix": "保留确定边、候选边、机制、源码证据与置信度；只有目标唯一且规则可靠时升级为确定边。",
            "risk": "框架约定和字符串路由易产生误报，不能为提高边数而建立猜测性依赖。",
        },
    ]
    for cluster in clusters:
        cluster["affected_project_count"] = len(cluster["affected_projects"])
    return clusters


def _render_clusters(clusters: list[dict[str, Any]]) -> str:
    lines = [
        "# 阶段一解析完整性跨项目问题聚类",
        "",
        "本聚类在完成全部保留项目的修改前审计后生成。排序优先考虑身份错误、确定信息损失、跨项目影响和后续迁移正确性，不按单个仓库临时加规则。",
        "",
    ]
    for cluster in clusters:
        lines.extend(
            [
                f"## P{cluster['priority']} {cluster['category']}",
                "",
                f"- 聚类 ID：`{cluster['cluster_id']}`",
                f"- 动机：{cluster['motivation']}",
                f"- 影响项目：{cluster['affected_project_count']} 个"
                + (
                    f"（{'、'.join(cluster['affected_projects'])}）"
                    if cluster["affected_projects"]
                    else "（当前基线未发现缺口，作为防回归契约保留）"
                ),
                f"- 通用修改方向：{cluster['planned_fix']}",
                f"- 风险：{cluster['risk']}",
                "",
                "修改前指标：",
                "",
                "```json",
                __import__("json").dumps(
                    cluster["before_metrics"], ensure_ascii=False, indent=2
                ),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    paths = {
        "pipeline_success_count": ("pipeline_success_count",),
        "files_missing": ("files", "missing_artifacts"),
        "files_collisions": ("files", "output_collisions"),
        "xaml_unclassified": ("xaml", "silently_unclassified_nodes"),
        "xaml_migration_dropped_visual_nodes": ("xaml", "migration_dropped_visual_nodes"),
        "xaml_structured_bindings": ("xaml", "structured_extractions", "binding"),
        "xaml_structured_commands": ("xaml", "structured_extractions", "command"),
        "xaml_structured_events": ("xaml", "structured_extractions", "event_handler"),
        "xaml_structured_static_resources": ("xaml", "structured_extractions", "static_resource"),
        "unsupported_total": ("unsupported_count",),
        "csharp_error_nodes": ("csharp", "tree_sitter_error_nodes"),
        "csharp_reported_error_nodes": ("csharp", "parser_reported_error_nodes"),
        "csharp_unreported_diagnostics": ("csharp", "unreported_tree_sitter_diagnostics"),
        "csharp_declaration_gap": ("csharp", "declaration_gap_total"),
        "csharp_partial_type_groups": ("csharp", "partial_type_groups"),
        "csharp_dependency_evidence": ("csharp", "dependency_evidence"),
        "csharp_unresolved": ("csharp", "unresolved_dependencies"),
        "resource_resolved": ("resources", "resolved_references"),
        "resource_unexplained": ("resources", "unexplained_references"),
        "resource_parser_source_ids": ("resources", "parser_resource_source_ids"),
        "resource_parser_links": ("resources", "parser_linked_references"),
        "resource_parser_unexplained": ("resources", "parser_unexplained_references"),
        "page_certain_edges": ("pages", "certain_edges"),
        "page_certain_edge_evidence": ("pages", "certain_edge_evidence"),
        "page_navigation_candidates": ("pages", "navigation_candidates"),
        "page_parser_candidates": ("pages", "parser_candidate_edges"),
        "unresolved_total": ("unresolved_count",),
    }

    def value(data: dict[str, Any], path: tuple[str, ...]) -> int:
        current: Any = data
        for key in path:
            current = current.get(key, 0) if isinstance(current, dict) else 0
        return int(current)

    comparison: dict[str, dict[str, int | float]] = {
        name: {
            "before": value(before, path),
            "after": value(after, path),
            "delta": value(after, path) - value(before, path),
        }
        for name, path in paths.items()
    }
    rate_paths = {
        "parser_rate_overall_percent": ("parser_rates", "overall", "percentage"),
        **{
            f"parser_rate_{parser_id}_percent": (
                "parser_rates",
                "parsers",
                parser_id,
                "percentage",
            )
            for parser_id in (
                "cs_parser",
                "xaml_parser",
                "cs_dependency",
                "indirect_resource_dependency",
                "page_dependency",
                "resource_dependency",
                "control_dependency",
            )
        },
    }

    def decimal_value(data: dict[str, Any], path: tuple[str, ...]) -> float:
        current: Any = data
        for key in path:
            current = current.get(key, 0) if isinstance(current, dict) else 0
        return round(float(current), 2)

    for name, path in rate_paths.items():
        before_value = decimal_value(before, path)
        after_value = decimal_value(after, path)
        comparison[name] = {
            "before": before_value,
            "after": after_value,
            "delta": round(after_value - before_value, 2),
        }
    return comparison


def _render_comparison(
    comparison: dict[str, dict[str, int | float]],
) -> str:
    lines = [
        "# 阶段一解析完整性前后对比",
        "",
        "下表使用同一版审计器比较冻结的修改前解析产物与修改后的第一次全量解析产物。正负增量只表示指标方向，具体含义需结合指标名称判断。",
        "",
        "| 指标 | 修改前 | 修改后 | 增量 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, values in comparison.items():
        is_rate = name.startswith("parser_rate_")
        before = (
            f"{float(values['before']):.2f}%" if is_rate else str(values["before"])
        )
        after = (
            f"{float(values['after']):.2f}%" if is_rate else str(values["after"])
        )
        delta = (
            f"{float(values['delta']):+.2f} 个百分点"
            if is_rate
            else f"{int(values['delta']):+d}"
        )
        lines.append(
            f"| `{name}` | {before} | {after} | {delta} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-root", type=Path, default=DEFAULT_BEFORE)
    parser.add_argument("--after-root", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    reports = _reports(args.before_root)
    clusters = build_clusters(reports)
    write_json(
        args.output_root / "issue-clusters.json",
        {"schema_version": 1, "project_count": len(reports), "clusters": clusters},
    )
    cluster_markdown = args.output_root / "issue-clusters.md"
    cluster_markdown.parent.mkdir(parents=True, exist_ok=True)
    cluster_markdown.write_text(_render_clusters(clusters), encoding="utf-8")
    print(f"问题聚类: {cluster_markdown}")

    if args.after_root:
        before = read_json(args.before_root / "audit-index.json")["aggregate"]
        after = read_json(args.after_root / "audit-index.json")["aggregate"]
        comparison = _comparison(before, after)
        write_json(
            args.output_root / "before-after-comparison.json",
            {"schema_version": 1, "metrics": comparison},
        )
        comparison_markdown = args.output_root / "before-after-comparison.md"
        comparison_markdown.write_text(
            _render_comparison(comparison), encoding="utf-8"
        )
        print(f"前后对比: {args.output_root / 'before-after-comparison.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
