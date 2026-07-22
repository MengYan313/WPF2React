"""从确定性 Parser 产物构建初始 evaluation manifest。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

from src.common.source_identity import (
    SOURCE_ID_SCHEME,
    normalize_page_id,
    target_relative_path,
)

from .models import (
    CallEdgeSpec,
    ComponentSpec,
    EvaluationManifest,
    PageSpec,
)


_TEXT_ATTRIBUTE_NAMES = (
    "Content",
    "Text",
    "Header",
    "Title",
    "AutomationProperties.Name",
)


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _iter_nodes(
    node: dict[str, Any],
    node_path: str = "root",
) -> Iterator[tuple[str, dict[str, Any]]]:
    yield node_path, node
    for index, child in enumerate(node.get("children", [])):
        yield from _iter_nodes(child, f"{node_path}.{index}")


def _page_target_hints(page_id: str) -> list[str]:
    target = target_relative_path(page_id, ".tsx").as_posix()
    return [
        target,
        f"src/{target}",
        f"src/pages/{target}",
    ]


def _clean_hint(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    if not normalized or normalized.startswith("{") or len(normalized) > 120:
        return None
    return normalized


def _text_hints(node: dict[str, Any]) -> list[str]:
    attributes = node.get("attributes", {})
    hints: list[str] = []
    for name in _TEXT_ATTRIBUTE_NAMES:
        cleaned = _clean_hint(attributes.get(name))
        if cleaned and cleaned not in hints:
            hints.append(cleaned)

    if not node.get("children"):
        source_code = str(node.get("source_code", ""))
        without_tags = re.sub(r"<[^>]+>", " ", source_code)
        cleaned = _clean_hint(without_tags)
        if cleaned and cleaned not in hints:
            hints.append(cleaned)
    return hints


def _target_tag_hints(
    source_tag: str,
    mappings: dict[str, Any],
) -> list[str]:
    normalized_tag = source_tag.split(":")[-1]
    hints: list[str] = []
    mapping = mappings.get(normalized_tag, {})
    mapped = mapping.get("mui_component") if isinstance(mapping, dict) else None
    if isinstance(mapped, str) and mapped.strip():
        hints.append(mapped.strip())
    if normalized_tag not in hints:
        hints.append(normalized_tag)
    return hints


def build_evaluation_manifest(
    project_id: str,
    *,
    output_base_dir: str | Path = "outputs",
    target_root: str | Path | None = None,
    mapping_path: str | Path = "rags/mui/wpf_to_mui_mapping.json",
) -> EvaluationManifest:
    """基于 control/page dependency JSON 构建待人工冻结的初始清单。"""
    dependency_dir = Path(output_base_dir) / project_id / "dependency"
    page_dependency_path = dependency_dir / "page_dependency.json"
    if not page_dependency_path.is_file():
        raise FileNotFoundError(f"页面依赖产物不存在: {page_dependency_path}")

    mappings: dict[str, Any] = {}
    resolved_mapping_path = Path(mapping_path)
    if resolved_mapping_path.is_file():
        loaded = _read_json(resolved_mapping_path)
        if isinstance(loaded, dict):
            mappings = loaded

    page_dependency = _read_json(page_dependency_path)
    if page_dependency.get("id_scheme") != SOURCE_ID_SCHEME:
        raise ValueError(
            f"页面依赖产物未使用 {SOURCE_ID_SCHEME}；请重新运行阶段 1 解析器"
        )
    pages_info = page_dependency.get("pages", {})
    ordered_pages = list(page_dependency.get("migration_order", []))
    for page_id in pages_info:
        if page_id not in ordered_pages:
            ordered_pages.append(page_id)

    pages: list[PageSpec] = []
    components: list[ComponentSpec] = []
    call_edges: list[CallEdgeSpec] = []

    for page_id in ordered_pages:
        page_id = normalize_page_id(page_id)
        page_info = pages_info.get(page_id, {})
        control_file = page_info.get("control_file")
        if not control_file:
            raise ValueError(f"页面 {page_id} 缺少 control_file")
        control_path = Path(output_base_dir) / project_id / control_file
        if not control_path.is_file():
            raise FileNotFoundError(f"控件依赖产物不存在: {control_path}")
        control_data = _read_json(control_path)
        if control_data.get("id_scheme") != SOURCE_ID_SCHEME:
            raise ValueError(
                f"页面 {page_id} 的控件产物未使用 {SOURCE_ID_SCHEME}"
            )
        if control_data.get("page_id") != page_id:
            raise ValueError(
                f"页面 {page_id} 与控件产物 ID {control_data.get('page_id')!r} 不一致"
            )
        source_file = str(
            control_data.get("source_file")
            or page_info.get("xaml_file")
            or ""
        )
        file_hints = _page_target_hints(page_id)
        pages.append(
            PageSpec(
                page_id=page_id,
                source_file=source_file,
                target_file_hints=file_hints,
            )
        )

        controls = control_data.get("controls")
        if not isinstance(controls, dict) or not controls:
            continue
        extracted_count = 0
        for node_path, node in _iter_nodes(controls):
            extracted_count += 1
            attributes = {
                str(key): str(value)
                for key, value in node.get("attributes", {}).items()
            }
            source_name = attributes.get("Name") or attributes.get("x:Name")
            source_tag = str(node.get("tag", ""))
            symbol_hints = [hint for hint in (source_name,) if hint]
            components.append(
                ComponentSpec(
                    component_id=f"{page_id}:{node_path}",
                    page_id=page_id,
                    source_file=source_file,
                    source_node_path=node_path,
                    source_tag=source_tag,
                    source_name=source_name,
                    source_attributes=attributes,
                    target_file_hints=file_hints,
                    target_symbol_hints=symbol_hints,
                    target_tag_hints=_target_tag_hints(source_tag, mappings),
                    text_hints=_text_hints(node),
                )
            )

        declared_count = control_data.get("control_count")
        if isinstance(declared_count, int) and declared_count != extracted_count:
            raise ValueError(
                f"{page_id} 的 control_count={declared_count}，"
                f"但实际遍历得到 {extracted_count} 个节点"
            )

        for target_page in page_info.get("dependencies", []):
            call_edges.append(
                CallEdgeSpec(
                    edge_id=f"{page_id}->{target_page}",
                    source_page=page_id,
                    target_page=target_page,
                )
            )

    return EvaluationManifest(
        project_id=project_id,
        target_root=str(target_root or Path("results") / project_id),
        components=components,
        pages=pages,
        call_edges=call_edges,
        metadata={
            "id_scheme": SOURCE_ID_SCHEME,
            "source": "parser_outputs",
            "page_dependency": str(page_dependency_path),
            "component_mapping": str(resolved_mapping_path),
            "review_status": "unreviewed",
            "note": "该清单是规则抽取初稿；正式实验前应独立核验并冻结。",
        },
    )
