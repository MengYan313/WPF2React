"""XAML 节点分类与迁移所需语义引用的确定性提取。"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .wpf_base_controls import WPF_BASE_CONTROLS


PRESENTATION_NAMESPACE = "http://schemas.microsoft.com/winfx/2006/xaml/presentation"
XAML_NAMESPACE = "http://schemas.microsoft.com/winfx/2006/xaml"

CONTAINER_TAGS = frozenset(
    {
        "Canvas",
        "DockPanel",
        "Grid",
        "Panel",
        "StackPanel",
        "UniformGrid",
        "Viewbox",
        "VirtualizingPanel",
        "VirtualizingStackPanel",
        "WrapPanel",
    }
)
ROOT_TAGS = frozenset(
    {
        "Application",
        "NavigationWindow",
        "Page",
        "ResourceDictionary",
        "UserControl",
        "Window",
    }
)
RESOURCE_TAGS = frozenset(
    {
        "ControlTemplate",
        "DataTemplate",
        "DataTrigger",
        "HierarchicalDataTemplate",
        "MultiDataTrigger",
        "MultiTrigger",
        "ResourceDictionary",
        "Setter",
        "Style",
        "Trigger",
    }
)
NONVISUAL_TAGS = frozenset(
    {
        "Binding",
        "ColumnDefinition",
        "Condition",
        "DynamicResource",
        "EventSetter",
        "InputBinding",
        "KeyBinding",
        "MultiBinding",
        "PriorityBinding",
        "RelativeSource",
        "RowDefinition",
        "Run",
        "StaticResource",
    }
)
EVENT_ATTRIBUTES = frozenset(
    {
        "Activated",
        "Checked",
        "Click",
        "Closed",
        "Closing",
        "DataContextChanged",
        "DoubleClick",
        "DragEnter",
        "DragLeave",
        "DragOver",
        "Drop",
        "GotFocus",
        "Initialized",
        "KeyDown",
        "KeyUp",
        "Loaded",
        "LostFocus",
        "MouseDoubleClick",
        "MouseDown",
        "MouseEnter",
        "MouseLeave",
        "MouseMove",
        "MouseUp",
        "Navigated",
        "Navigating",
        "Opened",
        "Selected",
        "SelectionChanged",
        "TextChanged",
        "Unchecked",
        "Unloaded",
        "ValueChanged",
    }
)
RESOURCE_PATH_ATTRIBUTES = frozenset(
    {
        "Cursor",
        "FontFamily",
        "Icon",
        "ImageSource",
        "NavigateUri",
        "Source",
        "UriSource",
    }
)
RESOURCE_EXTENSIONS = frozenset(
    {
        ".avi",
        ".bmp",
        ".csv",
        ".cur",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".json",
        ".m4a",
        ".mp3",
        ".mp4",
        ".otf",
        ".pdf",
        ".png",
        ".resx",
        ".svg",
        ".tif",
        ".tiff",
        ".ttf",
        ".txt",
        ".wav",
        ".webm",
        ".webp",
        ".wmv",
        ".woff",
        ".woff2",
        ".xml",
        ".xaml",
        ".yaml",
        ".yml",
    }
)


def classify_node(
    tag: str,
    namespace: str | None,
    *,
    parent_tags: Iterable[str],
    is_root: bool,
) -> tuple[str, str]:
    """把每个 XAML 元素归入一个且仅一个可审计类别。"""
    namespace = namespace or ""
    ancestors = list(parent_tags)
    if is_root and tag in ROOT_TAGS:
        return "page_or_document_root", "文档根节点"
    if "." in tag:
        return "property_element", "属性元素"
    if tag in RESOURCE_TAGS:
        return "resource_node", "资源、样式、模板或触发器节点"

    for ancestor in reversed(ancestors):
        if ancestor in {"ControlTemplate", "DataTemplate", "ItemsPanelTemplate"}:
            break
        if ancestor.endswith(".Resources") or ancestor in {
            "ResourceDictionary",
            "Setter",
            "Style",
            "Trigger",
            "DataTrigger",
            "MultiTrigger",
            "MultiDataTrigger",
        }:
            return "resource_node", "位于资源字典、样式、Setter 或触发器中"

    if tag in CONTAINER_TAGS:
        return "container", "WPF 布局容器"
    if tag in WPF_BASE_CONTROLS:
        return "base_control", "当前迁移控件树支持的 WPF 基础控件"
    if tag in NONVISUAL_TAGS:
        return "nonvisual_node", "绑定、布局定义或其他非视觉节点"
    if namespace and namespace not in {PRESENTATION_NAMESPACE, XAML_NAMESPACE}:
        lowered_namespace = namespace.casefold()
        lowered_tag = tag.casefold()
        if namespace.startswith("http://schemas.microsoft.com/expression/"):
            return "nonvisual_node", "设计期命名空间节点"
        if (
            "clr-namespace:system" in lowered_namespace
            or "converter" in lowered_namespace
            or "validator" in lowered_namespace
            or "behaviors" in lowered_namespace
            or "interactivity" in lowered_namespace
            or lowered_tag.endswith(
                ("action", "behavior", "converter", "extension", "trigger")
            )
        ):
            return "nonvisual_node", "系统值、转换器、验证器或行为对象"
        return "custom_control", "非 WPF 默认命名空间节点"
    if namespace == XAML_NAMESPACE:
        return "nonvisual_node", "XAML 语言命名空间节点"
    return "unsupported_node", "尚未识别的 WPF 元素类别"


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1] if "}" in value else value


def _target_from_markup(value: str, start: int, kind: str) -> str | None:
    fragment = value[start:]
    if kind in {"static_resource", "dynamic_resource"}:
        match = re.match(
            r"\{(?:StaticResource|DynamicResource)\s+([^,}\s]+)",
            fragment,
            re.IGNORECASE,
        )
        return match.group(1) if match else None
    match = re.match(
        r"\{(?:Binding|MultiBinding|PriorityBinding)(?:\s+([^,}\s]+))?",
        fragment,
        re.IGNORECASE,
    )
    positional = match.group(1) if match else None
    path_match = re.search(r"\bPath\s*=\s*([^,}]+)", fragment, re.IGNORECASE)
    return path_match.group(1).strip() if path_match else positional


def _looks_like_resource_path(value: str) -> bool:
    normalized = value.strip().strip("\"'").replace("\\", "/")
    lowered = normalized.casefold()
    if lowered.startswith(("http:", "https:", "pack:")) or ";component/" in lowered:
        return True
    candidate = normalized.split("?", 1)[0].split("#", 1)[0]
    suffix = "." + candidate.rsplit(".", 1)[-1].casefold() if "." in candidate else ""
    return suffix in RESOURCE_EXTENSIONS


def extract_semantic_references(
    *,
    tag: str,
    attributes: Mapping[str, str],
    attribute_details: Iterable[Mapping[str, Any]],
    node_path: str,
    source_line: int | None,
) -> list[dict[str, Any]]:
    """从节点及其属性中提取稳定、保留原值的迁移语义引用。"""
    references: list[dict[str, Any]] = []
    details = sorted(
        attribute_details,
        key=lambda item: (str(item.get("name", "")), str(item.get("full_name", ""))),
    )
    for detail in details:
        attr_name = str(detail.get("name", ""))
        raw_value = str(detail.get("value", ""))
        for markup_name, kind in (
            ("MultiBinding", "multibinding"),
            ("PriorityBinding", "prioritybinding"),
            ("Binding", "binding"),
            ("StaticResource", "static_resource"),
            ("DynamicResource", "dynamic_resource"),
        ):
            for match in re.finditer(
                r"\{" + markup_name + r"\b", raw_value, re.IGNORECASE
            ):
                target = _target_from_markup(raw_value, match.start(), kind)
                references.append(
                    {
                        "kind": kind,
                        "attribute": attr_name,
                        "target": target,
                        "raw_value": raw_value,
                        "resolution": "parsed" if target else "partial",
                        "node_path": node_path,
                        "source_line": source_line,
                    }
                )
        if attr_name == "Command":
            references.append(
                {
                    "kind": "command",
                    "attribute": attr_name,
                    "target": raw_value,
                    "raw_value": raw_value,
                    "resolution": "candidate" if "{" in raw_value else "parsed",
                    "node_path": node_path,
                    "source_line": source_line,
                }
            )
        elif attr_name == "CommandParameter":
            references.append(
                {
                    "kind": "command_parameter",
                    "attribute": attr_name,
                    "target": raw_value,
                    "raw_value": raw_value,
                    "resolution": "parsed",
                    "node_path": node_path,
                    "source_line": source_line,
                }
            )
        if (
            attr_name in EVENT_ATTRIBUTES or attr_name.startswith("Preview")
        ) and re.fullmatch(r"[A-Za-z_]\w*", raw_value.strip()):
            references.append(
                {
                    "kind": "event_handler",
                    "attribute": attr_name,
                    "target": raw_value.strip(),
                    "raw_value": raw_value,
                    "resolution": "parsed",
                    "node_path": node_path,
                    "source_line": source_line,
                }
            )
        if attr_name in RESOURCE_PATH_ATTRIBUTES and _looks_like_resource_path(raw_value):
            references.append(
                {
                    "kind": "file_resource",
                    "attribute": attr_name,
                    "target": raw_value,
                    "raw_value": raw_value,
                    "resolution": "candidate",
                    "node_path": node_path,
                    "source_line": source_line,
                }
            )

    explicit_kind = {
        "Binding": "binding",
        "MultiBinding": "multibinding",
        "PriorityBinding": "prioritybinding",
        "StaticResource": "static_resource",
        "DynamicResource": "dynamic_resource",
    }.get(tag)
    if explicit_kind:
        target = attributes.get("Path") or attributes.get("ResourceKey")
        references.append(
            {
                "kind": explicit_kind,
                "attribute": None,
                "target": target,
                "raw_value": None,
                "resolution": "parsed" if target else "partial",
                "node_path": node_path,
                "source_line": source_line,
            }
        )

    return sorted(
        references,
        key=lambda item: (
            str(item["kind"]),
            str(item.get("attribute") or ""),
            str(item.get("target") or ""),
            str(item.get("raw_value") or ""),
        ),
    )
