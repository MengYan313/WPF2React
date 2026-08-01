"""冻结实验页面集合的轻量读取契约。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.source_identity import normalize_page_id
from src.parser.io_utils import read_json


@dataclass(frozen=True)
class ProjectPageSelection:
    project_id: str
    page_ids: tuple[str, ...]
    manual_edges: tuple[dict[str, Any], ...]


def load_page_set_document(path: str | Path) -> dict[str, Any]:
    """读取当前完整页集。"""
    return read_json(path)


def load_project_page_selection(
    path: str | Path,
    project_id: str,
) -> ProjectPageSelection:
    """读取一个项目的冻结页面 ID 与人工静态审计边。"""
    document = load_page_set_document(path)
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
        project_id=project_id,
        page_ids=page_ids,
        manual_edges=manual_edges,
    )
