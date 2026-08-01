"""冻结实验页面集合的轻量读取契约。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.source_identity import SOURCE_ID_SCHEME, normalize_page_id
from src.parser.io_utils import read_json


@dataclass(frozen=True)
class ProjectPageSelection:
    selection_id: str
    project_id: str
    page_ids: tuple[str, ...]
    manual_edges: tuple[dict[str, Any], ...]


def load_page_set_document(path: str | Path) -> dict[str, Any]:
    """读取完整页集，或将增量版本合并到其基础版本。"""
    path = Path(path)
    document = read_json(path)
    if "extends" not in document:
        return document

    base = load_page_set_document(path.parent / document["extends"])
    projects = {item["project"]: dict(item) for item in base["projects"]}
    for update in document["project_updates"]:
        project = projects[update["project"]]
        project["pages"] = [*project["pages"], *update.get("add_pages", [])]
        project["manual_edges"] = [
            *project.get("manual_edges", []),
            *update.get("add_manual_edges", []),
        ]
        project["page_reviews"] = [
            *project.get("page_reviews", []),
            *update.get("page_reviews", []),
        ]
        if "addition_rationale" in update:
            project["rationale"] += f" v2 扩充：{update['addition_rationale']}"
        if "boundary_note" in update:
            project["boundary_note"] = update["boundary_note"]

    overrides = {
        key: value
        for key, value in document.items()
        if key not in {"extends", "project_updates", "selection_policy_overrides"}
    }
    return {
        **base,
        **overrides,
        "selection_policy": {
            **base["selection_policy"],
            **document.get("selection_policy_overrides", {}),
        },
        "projects": list(projects.values()),
    }


def load_project_page_selection(
    path: str | Path,
    project_id: str,
) -> ProjectPageSelection:
    """读取一个项目的冻结页面 ID 与人工静态审计边。"""
    document = load_page_set_document(path)
    if document.get("id_scheme") != SOURCE_ID_SCHEME:
        raise ValueError(f"实验页面集合未使用 {SOURCE_ID_SCHEME}")
    project = next(
        (
            item
            for item in document.get("projects", [])
            if item.get("project") == project_id
        ),
        None,
    )
    if project is None:
        raise ValueError(f"实验页面集合不包含项目: {project_id}")

    page_ids = tuple(normalize_page_id(page_id) for page_id in project["pages"])
    if not page_ids or len(page_ids) != len(set(page_ids)):
        raise ValueError(f"{project_id} 的实验页面为空或重复")
    selected = set(page_ids)
    manual_edges = tuple(project.get("manual_edges", []))
    for edge in manual_edges:
        if edge.get("source") not in selected or edge.get("target") not in selected:
            raise ValueError(f"{project_id} 的人工页面边越出冻结集合")

    return ProjectPageSelection(
        selection_id=document["selection_id"],
        project_id=project_id,
        page_ids=page_ids,
        manual_edges=manual_edges,
    )
