"""用阶段一结果验证并展开冻结的实验页面集合。"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser.io_utils import read_json, write_json
from src.migration.experiment_page_set import load_page_set_document


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _validate_manual_edge(project: str, edge: dict, selected: set[str]) -> dict:
    if edge["source"] not in selected or edge["target"] not in selected:
        raise ValueError(f"{project} 人工边端点不在页面集合中: {edge}")

    evidence_path = PROJECT_ROOT / "repos" / project / edge["evidence_file"]
    lines = evidence_path.read_text(encoding="utf-8-sig").splitlines()
    line = lines[edge["evidence_line"] - 1]
    if edge["evidence_excerpt"] not in line:
        raise ValueError(
            f"{project} 人工边证据已漂移: {edge['evidence_file']}:{edge['evidence_line']}"
        )
    return {**edge, "origin": "manual_source_audit"}


def _phase1_edge(source: str, target: str, page: dict) -> dict:
    evidence = next(
        item for item in page["dependency_evidence"] if item["target_page_id"] == target
    )
    return {
        "source": source,
        "target": target,
        "relation": "static_page_reference",
        "confidence": evidence["confidence"],
        "method": evidence["resolution"],
        "evidence_file": page["cs_source_id"],
        "evidence_line": evidence["source_line"],
        "evidence_excerpt": evidence["evidence"],
        "origin": "phase1_page_dependency",
    }


def build_page_set(
    spec_path: Path,
    parser_root: Path,
    statistics_path: Path,
) -> dict:
    spec = load_page_set_document(spec_path)
    statistics = read_json(statistics_path)
    taxonomy = statistics["taxonomy"]["projects"]
    projects = {item["project"] for item in spec["projects"]}
    if projects != set(taxonomy):
        raise ValueError("冻结页集与数据集分类的项目集合不一致")

    max_controls = spec["selection_policy"]["maximum_control_count_per_page"]
    expanded_projects = []
    all_edges = []
    all_boundary_edges = []
    root_tags = Counter()
    role_summary: dict[str, Counter] = {}

    for project_spec in spec["projects"]:
        project = project_spec["project"]
        dependency_path = parser_root / project / "dependency/page_dependency.json"
        dependency = read_json(dependency_path)
        selected_ids = project_spec["pages"]
        selected = set(selected_ids)
        if len(selected) != len(selected_ids):
            raise ValueError(f"{project} 存在重复 page ID")

        pages = []
        phase1_edges = []
        boundary_edges = []
        for page_id in selected_ids:
            if page_id not in dependency["pages"]:
                raise ValueError(f"{project} 阶段一结果缺少页面: {page_id}")
            page_graph = dependency["pages"][page_id]
            control_path = (
                parser_root / project / "dependency/controls" / f"{page_id}.json"
            )
            control = read_json(control_path)
            if control["page_id"] != page_id:
                raise ValueError(f"{project} 控件树页面 ID 契约不一致: {page_id}")
            if control["control_count"] > max_controls:
                raise ValueError(f"{project} 页面超过控件数上限: {page_id}")

            root_tag = control["root_info"]["tag"]
            root_tags[root_tag] += 1
            page = {
                "page_id": page_id,
                "component_name": page_graph["component_name"],
                "source_class_full_name": page_graph["source_class_full_name"],
                "root_tag": root_tag,
                "control_count": control["control_count"],
                "custom_control_count": len(control["custom_controls"]),
                "unsupported_node_count": len(control["unsupported_nodes"]),
                "migration_order": page_graph["migration_order"],
                "control_file": _relative(control_path),
            }
            review = next(
                (
                    item
                    for item in project_spec.get("page_reviews", [])
                    if item["page_id"] == page_id
                ),
                None,
            )
            if review:
                page["selection_review"] = review
            pages.append(page)
            for target in page_graph["dependencies"]:
                edge = _phase1_edge(page_id, target, page_graph)
                if target in selected:
                    phase1_edges.append(edge)
                else:
                    boundary_edges.append(edge)

        manual_edges = [
            _validate_manual_edge(project, edge, selected)
            for edge in project_spec["manual_edges"]
        ]
        keys = [
            (edge["source"], edge["target"])
            for edge in phase1_edges + manual_edges
        ]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{project} 页面调用边重复")

        project_edges = phase1_edges + manual_edges
        project_totals = {
            "pages": len(pages),
            "controls": sum(page["control_count"] for page in pages),
            "custom_controls": sum(page["custom_control_count"] for page in pages),
            "unsupported_nodes": sum(page["unsupported_node_count"] for page in pages),
            "call_edges": len(project_edges),
            "phase1_edges": len(phase1_edges),
            "manual_edges": len(manual_edges),
            "phase1_boundary_edges": len(boundary_edges),
        }
        role = taxonomy[project]["role"]
        role_summary.setdefault(role, Counter()).update(project_totals)
        role_summary[role]["projects"] += 1
        expanded_projects.append(
            {
                "project": project,
                "taxonomy": taxonomy[project],
                "rationale": project_spec["rationale"],
                "boundary_note": project_spec["boundary_note"],
                "totals": project_totals,
                "pages": pages,
                "call_edges": project_edges,
                "phase1_boundary_edges": boundary_edges,
            }
        )
        all_edges.extend({"project": project, **edge} for edge in project_edges)
        all_boundary_edges.extend(
            {"project": project, **edge} for edge in boundary_edges
        )

    selected_pages = sum(item["totals"]["pages"] for item in expanded_projects)
    selected_controls = sum(
        item["totals"]["controls"] for item in expanded_projects
    )
    linked_pages = {
        (edge["project"], page_id)
        for edge in all_edges
        for page_id in (edge["source"], edge["target"])
    }
    standalone_pages = [
        page
        for project in expanded_projects
        for page in project["pages"]
        if (project["project"], page["page_id"]) not in linked_pages
    ]
    max_standalone = spec["selection_policy"].get("maximum_standalone_pages")
    if max_standalone is not None and len(standalone_pages) > max_standalone:
        raise ValueError(
            f"独立页面超过冻结上限: {len(standalone_pages)} > {max_standalone}"
        )
    max_standalone_ratio = spec["selection_policy"].get(
        "maximum_standalone_page_ratio"
    )
    standalone_ratio = len(standalone_pages) / selected_pages
    if max_standalone_ratio is not None and standalone_ratio > max_standalone_ratio:
        raise ValueError(
            f"独立页面占比超过冻结上限: {standalone_ratio:.4f} > "
            f"{max_standalone_ratio:.4f}"
        )
    simple_limit = spec["selection_policy"]["simple_page_control_limit"]
    total_pages = statistics["included_dataset"]["pages"]
    return {
        "inputs": {
            "spec": _relative(spec_path),
            "phase1_root": _relative(parser_root),
            "dataset_statistics": _relative(statistics_path),
        },
        "selection_policy": spec["selection_policy"],
        "totals": {
            "projects": len(expanded_projects),
            "pages": selected_pages,
            "available_pages": total_pages,
            "page_selection_rate": round(selected_pages / total_pages, 6),
            "linked_pages": len(linked_pages),
            "standalone_pages": len(standalone_pages),
            "standalone_page_ratio": round(standalone_ratio, 6),
            "simple_standalone_pages": sum(
                page["control_count"] <= simple_limit for page in standalone_pages
            ),
            "controls": selected_controls,
            "custom_controls": sum(
                item["totals"]["custom_controls"] for item in expanded_projects
            ),
            "unsupported_nodes": sum(
                item["totals"]["unsupported_nodes"] for item in expanded_projects
            ),
            "call_edges": len(all_edges),
            "phase1_edges": sum(
                edge["origin"] == "phase1_page_dependency" for edge in all_edges
            ),
            "manual_edges": sum(
                edge["origin"] == "manual_source_audit" for edge in all_edges
            ),
            "phase1_boundary_edges": len(all_boundary_edges),
        },
        "root_tag_distribution": dict(sorted(root_tags.items())),
        "role_summary": {
            role: dict(counts) for role, counts in sorted(role_summary.items())
        },
        "projects": expanded_projects,
        "call_graph": all_edges,
        "phase1_boundary_edges": all_boundary_edges,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spec", default="docs/research/experiment-page-set.json"
    )
    parser.add_argument(
        "--parser-root", default="outputs/parser-completeness/current"
    )
    parser.add_argument(
        "--statistics", default="results/dataset/dataset-statistics.json"
    )
    parser.add_argument(
        "--output", default="results/dataset/experiment-page-set.json"
    )
    args = parser.parse_args()

    document = build_page_set(
        PROJECT_ROOT / args.spec,
        PROJECT_ROOT / args.parser_root,
        PROJECT_ROOT / args.statistics,
    )
    output_path = PROJECT_ROOT / args.output
    write_json(output_path, document)
    totals = document["totals"]
    print(
        f"已验证 {totals['projects']} 个项目、{totals['pages']} 个页面、"
        f"{totals['linked_pages']} 个联动页面、"
        f"{totals['standalone_pages']} 个独立页面、"
        f"{totals['controls']} 个控件、{totals['call_edges']} 条集合内页面边；"
        f"结果: {_relative(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
