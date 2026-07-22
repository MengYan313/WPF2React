"""审计阶段一解析产物的文件、结构、语义引用与资源闭包完整性。"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

import lxml.etree as ET
import tree_sitter_c_sharp as tscsharp
from tree_sitter import Language, Node, Parser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.source_identity import (
    SOURCE_ID_SCHEME,
    artifact_source_id,
    mirrored_json_path,
    repository_relative_id,
)
from src.parser.io_utils import read_json, write_json
from src.parser.path_utils import (
    IGNORED_SOURCE_DIRECTORIES,
    discover_project_files,
    is_ignored_source_path,
)
from src.parser.resource_dependency import ResourceDependencyAnalyzer
from src.parser.wpf_base_controls import WPF_BASE_CONTROLS


SELECTED_STATUSES = frozenset({"保留", "条件保留"})
DEFAULT_MANIFEST = Path("results/dataset/dataset-manifest.json")
DEFAULT_PARSE_ROOT = Path("outputs/parser-completeness/before")
DEFAULT_REPORT_ROOT = Path("results/parser-completeness/before")
PARSER_RATE_THRESHOLD = 0.90
PARSER_RATE_DEFINITIONS = {
    "cs_parser": {
        "label": "C# 结构解析器",
        "basis": "C# 文件产物、约定声明结构保留及 tree-sitter 诊断显式化",
    },
    "xaml_parser": {
        "label": "XAML/csproj 解析器",
        "basis": "XAML/csproj 文件产物、XML 元素 IR 与约定语义引用结构化",
    },
    "cs_dependency": {
        "label": "C# 依赖解析器",
        "basis": "依赖产物、确定边证据与候选依赖显式 unresolved",
    },
    "indirect_resource_dependency": {
        "label": "间接资源解析器",
        "basis": "间接资源、数据资源与模板资源三个约定产物",
    },
    "page_dependency": {
        "label": "页面依赖解析器",
        "basis": "页面产物、迁移顺序、确定边证据与导航候选显式分类",
    },
    "resource_dependency": {
        "label": "静态资源解析器",
        "basis": "资源产物、仓库资源清单与 XAML 资源引用显式分类",
    },
    "control_dependency": {
        "label": "控件依赖解析器",
        "basis": "页面控件产物与页面视觉节点在控件树或独立清单中的保留",
    },
}
PRESENTATION_NAMESPACE = "http://schemas.microsoft.com/winfx/2006/xaml/presentation"
XAML_NAMESPACE = "http://schemas.microsoft.com/winfx/2006/xaml"

CONTAINER_TAGS = frozenset(
    {
        "AdornerDecorator",
        "Canvas",
        "Decorator",
        "DockPanel",
        "Grid",
        "ItemsPanelTemplate",
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
        "BitmapImage",
        "ControlTemplate",
        "DataTemplate",
        "DrawingBrush",
        "GradientStop",
        "HierarchicalDataTemplate",
        "ImageBrush",
        "LinearGradientBrush",
        "RadialGradientBrush",
        "ResourceDictionary",
        "Setter",
        "SolidColorBrush",
        "Style",
        "Trigger",
        "DataTrigger",
        "MultiDataTrigger",
        "MultiTrigger",
    }
)
NONVISUAL_TAGS = frozenset(
    {
        "Binding",
        "BindingBase",
        "ColumnDefinition",
        "Condition",
        "EventSetter",
        "InputBinding",
        "KeyBinding",
        "MultiBinding",
        "PriorityBinding",
        "RelativeSource",
        "RowDefinition",
        "Run",
        "StaticResource",
        "DynamicResource",
        "TextDecoration",
        "TransformGroup",
        "TranslateTransform",
        "ScaleTransform",
        "RotateTransform",
        "SkewTransform",
        "MatrixTransform",
    }
)
NATIVE_VISUAL_TAGS = frozenset(
    {
        "ContentControl",
        "ContentPresenter",
        "Ellipse",
        "Frame",
        "ItemsControl",
        "ItemsPresenter",
        "Line",
        "ListBoxItem",
        "ListViewItem",
        "MediaElement",
        "MenuItem",
        "PasswordBox",
        "Path",
        "Polygon",
        "Polyline",
        "Rectangle",
        "Shape",
        "TabItem",
        "TextElement",
        "ToggleButton",
        "TreeViewItem",
        "Viewport3D",
    }
)
NATIVE_NONVISUAL_SUFFIXES = (
    "Animation",
    "AnimationUsingKeyFrames",
    "Binding",
    "Brush",
    "Color",
    "Column",
    "Command",
    "Converter",
    "Drawing",
    "Effect",
    "Geometry",
    "Gesture",
    "KeyFrame",
    "KeyFrames",
    "Pen",
    "Storyboard",
    "Transform",
    "Transition",
    "VisualState",
    "VisualStateGroup",
)
NATIVE_NONVISUAL_TAGS = frozenset(
    {
        "BeginStoryboard",
        "BlockUIContainer",
        "Bold",
        "Brush",
        "CommandBinding",
        "DiscreteObjectKeyFrame",
        "Figure",
        "Floater",
        "FlowDocument",
        "FrameworkElement",
        "GridView",
        "GridViewColumn",
        "InlineUIContainer",
        "Italic",
        "LineBreak",
        "List",
        "ListItem",
        "Paragraph",
        "Section",
        "Span",
        "StopStoryboard",
        "Table",
        "TableCell",
        "TableColumn",
        "TableRow",
        "TableRowGroup",
        "Thickness",
        "Underline",
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
RESOURCE_ATTRIBUTE_NAMES = frozenset(
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
    set(ResourceDependencyAnalyzer.RESOURCE_EXTENSIONS)
    | {".webp", ".webm", ".m4a", ".pdf", ".yaml", ".yml"}
)
BUILD_ACTIONS = frozenset(
    {
        "ApplicationDefinition",
        "Content",
        "EmbeddedResource",
        "None",
        "Page",
        "Resource",
        "SplashScreen",
    }
)
C_SHARP_DECLARATIONS = {
    "namespace_declaration": "namespace",
    "file_scoped_namespace_declaration": "namespace",
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "struct_declaration": "struct",
    "record_declaration": "record",
    "field_declaration": "field",
    "property_declaration": "property",
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "event_declaration": "event",
    "event_field_declaration": "event",
}
IR_DECLARATIONS = frozenset(
    {
        "namespace",
        "class",
        "interface",
        "enum",
        "struct",
        "record",
        "field",
        "property",
        "method",
        "constructor",
        "event",
    }
)
NAVIGATION_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("prism", r"\b(?:RequestNavigate|RegisterForNavigation|NavigateAsync)\s*[<(]", "medium"),
    ("prism-region", r"\bIRegionManager\b|\bRegionName\b", "low"),
    ("mvvmcross", r"\b(?:ShowViewModel|IMvxNavigationService|MvxNavigationService)\b", "medium"),
    ("dependency-injection", r"\b(?:GetRequiredService|GetService|Resolve)\s*<[^>]*(?:View|Window|Page)", "medium"),
    ("navigation-service", r"\bNavigationService\s*\.\s*Navigate\b", "high"),
    ("string-route", r"\b(?:Navigate|RequestNavigate)\s*\(\s*[\"'][^\"']+[\"']", "medium"),
    ("reflection", r"\b(?:Activator\.CreateInstance|Type\.GetType)\s*\(", "low"),
)


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1] if "}" in value else value


def _namespace(value: str) -> str:
    return value[1:].split("}", 1)[0] if value.startswith("{") else ""


def _read_text(path: Path) -> tuple[str | None, str | None]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), None
        except UnicodeDecodeError:
            continue
    return None, "无法使用 UTF-8、Windows-1252 或 Latin-1 解码"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _node_line(node: Node) -> int:
    return node.start_point[0] + 1


def _walk_ts(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _walk_ir(node: dict[str, Any] | None) -> Iterator[dict[str, Any]]:
    if not node:
        return
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        children = current.get("children", [])
        if isinstance(children, list):
            stack.extend(reversed([child for child in children if isinstance(child, dict)]))


def _control_tags(node: dict[str, Any] | None) -> list[str]:
    return [str(item.get("tag", "")) for item in _walk_ir(node)]


def _element_path(element: Any) -> str:
    parts: list[str] = []
    current = element
    while current is not None and isinstance(current.tag, str):
        name = _local_name(current.tag)
        parent = current.getparent()
        if parent is None:
            parts.append(name)
            break
        siblings = [
            child
            for child in parent
            if isinstance(child.tag, str) and _local_name(child.tag) == name
        ]
        index = siblings.index(current) + 1
        parts.append(f"{name}[{index}]")
        current = parent
    return "/" + "/".join(reversed(parts))


def _classify_xaml_element(element: Any, *, is_root: bool) -> tuple[str, str]:
    tag = _local_name(element.tag)
    namespace = _namespace(element.tag)
    if is_root and tag in ROOT_TAGS:
        return "page_or_document_root", "文档根节点"
    if "." in tag:
        return "property_element", "属性元素"
    if tag in RESOURCE_TAGS:
        return "resource_node", "资源、样式、模板或触发器节点"
    resource_context = False
    parent = element.getparent()
    while parent is not None and isinstance(parent.tag, str):
        parent_tag = _local_name(parent.tag)
        if parent_tag in {"ControlTemplate", "DataTemplate", "ItemsPanelTemplate"}:
            break
        if (
            parent_tag.endswith(".Resources")
            or parent_tag
            in {
                "ResourceDictionary",
                "Setter",
                "Style",
                "Trigger",
                "DataTrigger",
                "MultiTrigger",
                "MultiDataTrigger",
            }
        ):
            resource_context = True
            break
        parent = parent.getparent()
    if resource_context:
        return "resource_node", "位于资源字典、样式、Setter 或触发器中"
    if tag in CONTAINER_TAGS:
        return "container", "WPF 布局容器"
    if tag in WPF_BASE_CONTROLS or tag in NATIVE_VISUAL_TAGS:
        return "base_control", "WPF 内置视觉控件"
    if (
        tag in NONVISUAL_TAGS
        or tag in NATIVE_NONVISUAL_TAGS
        or tag.endswith(NATIVE_NONVISUAL_SUFFIXES)
    ):
        return "nonvisual_node", "绑定、布局定义、文本或变换等非视觉节点"
    if namespace and namespace not in {PRESENTATION_NAMESPACE, XAML_NAMESPACE}:
        if namespace.startswith("http://schemas.microsoft.com/expression/"):
            return "nonvisual_node", "设计期命名空间节点"
        lowered_namespace = namespace.casefold()
        lowered_tag = tag.casefold()
        if (
            "clr-namespace:system" in lowered_namespace
            or "converter" in lowered_namespace
            or "validator" in lowered_namespace
            or "behaviors" in lowered_namespace
            or "interactivity" in lowered_namespace
            or lowered_tag.endswith(("behavior", "converter", "extension", "trigger", "action"))
        ):
            return "nonvisual_node", "系统值、转换器、验证器或行为对象"
        return "custom_control", "非 WPF 默认命名空间节点"
    if namespace == XAML_NAMESPACE:
        return "nonvisual_node", "XAML 语言命名空间节点"
    return "unsupported_node", "未纳入基础控件、容器、资源或非视觉分类"


def _structured_semantic_counts(root: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for node in _walk_ir(root):
        for key in ("semantic_references", "structured_references"):
            references = node.get(key, [])
            if not isinstance(references, list):
                continue
            for reference in references:
                if isinstance(reference, dict) and reference.get("kind"):
                    counts[str(reference["kind"])] += 1
        semantics = node.get("semantics", {})
        if isinstance(semantics, dict):
            for kind, values in semantics.items():
                if isinstance(values, list):
                    counts[str(kind)] += len(values)
    return counts


def _extract_markup_occurrences(value: str, kind: str) -> list[re.Match[str]]:
    return list(re.finditer(r"\{" + re.escape(kind) + r"\b", value, re.IGNORECASE))


def _xaml_audit(
    project_path: Path,
    project_output: Path,
    xaml_files: list[Path],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    set[str],
    list[dict[str, Any]],
]:
    classification: Counter[str] = Counter()
    occurrences: Counter[str] = Counter()
    structured: Counter[str] = Counter()
    unsupported: list[dict[str, Any]] = []
    resource_references: list[dict[str, Any]] = []
    resource_keys: set[str] = set()
    navigation_candidates: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    raw_elements = 0
    ir_nodes = 0
    migration_control_nodes = 0
    migration_custom_nodes = 0
    migration_node_inventory_nodes = 0
    migration_preserved_visual_nodes = 0
    page_visual_nodes = 0
    page_custom_controls = 0
    page_xaml_files = 0
    control_artifacts = 0

    for source in xaml_files:
        source_id = repository_relative_id(source, project_path)
        text, read_error = _read_text(source)
        if text is None:
            parse_errors.append({"source_id": source_id, "reason": read_error})
            continue
        try:
            xml_root = ET.fromstring(
                text.encode("utf-8"),
                parser=ET.XMLParser(remove_blank_text=False, recover=False),
            )
        except Exception as exc:
            parse_errors.append({"source_id": source_id, "reason": str(exc)})
            continue

        sibling_names = {
            sibling.name.casefold()
            for sibling in source.parent.iterdir()
            if sibling.is_file()
        }
        paired_names = {
            f"{source.stem}.xaml.cs".casefold(),
            f"{source.stem}.cs".casefold(),
        }
        is_page_source = (
            _local_name(xml_root.tag) != "Application"
            and bool(sibling_names & paired_names)
        )
        page_xaml_files += int(is_page_source)

        artifact = mirrored_json_path(project_output / "xaml", source_id)
        parsed: dict[str, Any] = read_json(artifact) if artifact.exists() else {}
        parsed_root = parsed.get("root", {}) if isinstance(parsed, dict) else {}
        ir_nodes += sum(1 for _ in _walk_ir(parsed_root))
        structured.update(_structured_semantic_counts(parsed_root))

        control_artifact = mirrored_json_path(
            project_output / "dependency" / "controls", source_id
        )
        has_control_artifact = control_artifact.exists()
        control_artifacts += int(is_page_source and has_control_artifact)
        inventory_present = False
        file_control_tags: list[str] = []
        file_visual_nodes = 0
        if has_control_artifact:
            control_data = read_json(control_artifact)
            file_control_tags = [
                tag
                for tag in _control_tags(control_data.get("controls", {}))
                if tag and tag != "Root"
            ]
            migration_control_nodes += len(file_control_tags)
            inventory = control_data.get("node_inventory", [])
            if isinstance(inventory, list) and inventory:
                inventory_present = True
                migration_node_inventory_nodes += len(inventory)
                migration_custom_nodes += sum(
                    isinstance(item, dict)
                    and item.get("classification") == "custom_control"
                    for item in inventory
                )
            else:
                migration_custom_nodes += sum(
                    tag not in WPF_BASE_CONTROLS for tag in file_control_tags
                )

        for index, element in enumerate(xml_root.iter()):
            if not isinstance(element.tag, str):
                continue
            raw_elements += 1
            tag = _local_name(element.tag)
            category, reason = _classify_xaml_element(element, is_root=index == 0)
            classification[category] += 1
            if is_page_source and category in {
                "base_control",
                "container",
                "custom_control",
            }:
                file_visual_nodes += 1
                page_visual_nodes += 1
                page_custom_controls += category == "custom_control"
            node_path = _element_path(element)
            if category in {"custom_control", "unsupported_node"}:
                unsupported.append(
                    {
                        "source_id": source_id,
                        "line": getattr(element, "sourceline", None),
                        "node_path": node_path,
                        "tag": tag,
                        "namespace": _namespace(element.tag),
                        "classification": category,
                        "reason": reason,
                    }
                )

            if tag in {"Binding", "MultiBinding", "PriorityBinding"}:
                occurrences[tag.casefold()] += 1
            if tag in {"StaticResource", "DynamicResource"}:
                kind = "static_resource" if tag == "StaticResource" else "dynamic_resource"
                occurrences[kind] += 1
            if tag in {"Style", "Setter", "Trigger", "DataTrigger", "MultiTrigger", "MultiDataTrigger"}:
                occurrences[tag.casefold()] += 1
            if tag in {"DataTemplate", "ControlTemplate"}:
                occurrences[tag.casefold()] += 1
            if tag == "ResourceDictionary":
                occurrences["resource_dictionary"] += 1
            if tag == "ResourceDictionary.MergedDictionaries":
                occurrences["merged_dictionaries"] += 1

            clean_attributes = {_local_name(k): v for k, v in element.attrib.items()}
            if tag == "DataTemplate" and clean_attributes.get("DataType"):
                custom_descendants = [
                    _local_name(descendant.tag)
                    for descendant in element.iterdescendants()
                    if isinstance(descendant.tag, str)
                    and _namespace(descendant.tag)
                    not in {"", PRESENTATION_NAMESPACE, XAML_NAMESPACE}
                ]
                if custom_descendants:
                    navigation_candidates.append(
                        {
                            "source_id": source_id,
                            "line": getattr(element, "sourceline", None),
                            "mechanism": "mvvm-datatemplate-view-mapping",
                            "confidence": "medium",
                            "resolution": "candidate",
                            "source_symbol": clean_attributes["DataType"],
                            "target_symbol": custom_descendants[0],
                        }
                    )
            if "RegionName" in clean_attributes:
                navigation_candidates.append(
                    {
                        "source_id": source_id,
                        "line": getattr(element, "sourceline", None),
                        "mechanism": "prism-region",
                        "confidence": "medium",
                        "resolution": "candidate",
                        "target_symbol": clean_attributes["RegionName"],
                    }
                )
            for key_name in ("Key", "Name"):
                key_value = clean_attributes.get(key_name)
                if key_name == "Key" and key_value:
                    resource_keys.add(key_value)

            for attr_name, value in clean_attributes.items():
                for kind in ("MultiBinding", "PriorityBinding", "Binding"):
                    matches = _extract_markup_occurrences(value, kind)
                    occurrences[kind.casefold()] += len(matches)
                for kind in ("StaticResource", "DynamicResource"):
                    for match in _extract_markup_occurrences(value, kind):
                        key_match = re.match(
                            r"\{(?:StaticResource|DynamicResource)\s+([^,}\s]+)",
                            value[match.start() :],
                            re.IGNORECASE,
                        )
                        ref_kind = (
                            "static_resource" if kind == "StaticResource" else "dynamic_resource"
                        )
                        occurrences[ref_kind] += 1
                        resource_references.append(
                            {
                                "source_id": source_id,
                                "line": getattr(element, "sourceline", None),
                                "node_path": node_path,
                                "attribute": attr_name,
                                "kind": ref_kind,
                                "value": key_match.group(1) if key_match else value,
                                "raw_value": value,
                            }
                        )
                if attr_name == "Command":
                    occurrences["command"] += 1
                elif attr_name == "CommandParameter":
                    occurrences["command_parameter"] += 1
                if (
                    attr_name in EVENT_ATTRIBUTES or attr_name.startswith("Preview")
                ) and re.fullmatch(r"[A-Za-z_]\w*", value.strip()):
                    occurrences["event_handler"] += 1
                if attr_name in RESOURCE_ATTRIBUTE_NAMES:
                    suffix = PurePosixPath(value.replace("\\", "/").split("?", 1)[0]).suffix.lower()
                    if (
                        suffix in RESOURCE_EXTENSIONS
                        or ";component/" in value.casefold()
                        or value.casefold().startswith(("pack:", "http:", "https:"))
                    ):
                        occurrences["file_resource_reference"] += 1
                        resource_references.append(
                            {
                                "source_id": source_id,
                                "line": getattr(element, "sourceline", None),
                                "node_path": node_path,
                                "attribute": attr_name,
                                "kind": "file_resource",
                                "value": value,
                                "raw_value": value,
                            }
                        )

        if has_control_artifact:
            migration_preserved_visual_nodes += (
                file_visual_nodes if inventory_present else len(file_control_tags)
            )

    counts = {
        "raw_xml_elements": raw_elements,
        "xaml_ir_nodes": ir_nodes,
        "classification": dict(sorted(classification.items())),
        "base_controls": classification["base_control"],
        "custom_controls": classification["custom_control"],
        "containers": classification["container"],
        "property_elements": classification["property_element"],
        "resource_nodes": classification["resource_node"],
        "nonvisual_nodes": classification["nonvisual_node"],
        "unsupported_nodes": classification["unsupported_node"],
        "silently_unclassified_nodes": max(
            0, raw_elements - sum(classification.values())
        ),
        "migration_control_ir_nodes": migration_control_nodes,
        "migration_node_inventory_nodes": migration_node_inventory_nodes,
        "migration_preserved_visual_nodes": migration_preserved_visual_nodes,
        "migration_custom_control_nodes": migration_custom_nodes,
        "page_xaml_files": page_xaml_files,
        "control_artifacts": control_artifacts,
        "page_visual_nodes": page_visual_nodes,
        "page_custom_controls": page_custom_controls,
        "migration_dropped_visual_nodes": max(
            0, page_visual_nodes - migration_preserved_visual_nodes
        ),
        "occurrences": dict(sorted(occurrences.items())),
        "structured_extractions": dict(sorted(structured.items())),
        "parse_errors": parse_errors,
    }
    return counts, unsupported, resource_keys, navigation_candidates


def _find_identifier(node: Node, source: bytes) -> str:
    for child in node.children:
        if child.type == "identifier":
            return source[child.start_byte : child.end_byte].decode("utf-8")
    return ""


def _csharp_audit(
    project_path: Path,
    project_output: Path,
    cs_files: list[Path],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    parser = Parser(Language(tscsharp.language()))
    raw_counts: Counter[str] = Counter()
    ir_counts: Counter[str] = Counter()
    errors: list[dict[str, Any]] = []
    navigation_candidates: list[dict[str, Any]] = []
    type_definitions: defaultdict[str, set[str]] = defaultdict(set)
    partial_definitions: defaultdict[str, set[str]] = defaultdict(set)
    tree_roots = 0
    missing_nodes = 0
    parser_reported_error_nodes = 0
    parser_reported_missing_nodes = 0

    for source_path in cs_files:
        source_id = repository_relative_id(source_path, project_path)
        text, read_error = _read_text(source_path)
        if text is None:
            errors.append({"source_id": source_id, "reason": read_error})
            continue
        source = text.encode("utf-8")
        tree = parser.parse(source)
        tree_roots += 1
        for node in _walk_ts(tree.root_node):
            mapped = C_SHARP_DECLARATIONS.get(node.type)
            if mapped:
                if node.type in {"field_declaration", "event_field_declaration"}:
                    declaration = next(
                        (
                            child
                            for child in node.named_children
                            if child.type == "variable_declaration"
                        ),
                        None,
                    )
                    declarator_count = sum(
                        child.type == "variable_declarator"
                        for child in (
                            declaration.named_children if declaration else ()
                        )
                    )
                    raw_counts[mapped] += max(1, declarator_count)
                else:
                    raw_counts[mapped] += 1
                if mapped in {"class", "interface", "enum", "struct", "record"}:
                    name = _find_identifier(node, source)
                    if name:
                        type_definitions[name].add(source_id)
                        declaration_text = source[node.start_byte : node.end_byte].decode(
                            "utf-8", errors="replace"
                        )
                        if re.search(r"\bpartial\b", declaration_text[:300]):
                            partial_definitions[name].add(source_id)
            if node.type == "ERROR" or node.is_error:
                errors.append(
                    {
                        "source_id": source_id,
                        "line": _node_line(node),
                        "node_type": node.type,
                        "reason": "tree-sitter ERROR 节点",
                        "evidence": source[node.start_byte : min(node.end_byte, node.start_byte + 240)]
                        .decode("utf-8", errors="replace")
                        .strip(),
                    }
                )
            if node.is_missing:
                missing_nodes += 1
                errors.append(
                    {
                        "source_id": source_id,
                        "line": _node_line(node),
                        "node_type": node.type,
                        "reason": "tree-sitter 缺失节点",
                    }
                )

        artifact = mirrored_json_path(project_output / "cs", source_id)
        if artifact.exists():
            artifact_data = read_json(artifact)
            root = artifact_data.get("root", {})
            summary = artifact_data.get("tree_sitter_summary", {})
            parser_reported_error_nodes += int(summary.get("error_nodes", 0))
            parser_reported_missing_nodes += int(summary.get("missing_nodes", 0))
            for item in _walk_ir(root):
                node_type = str(item.get("node_type", ""))
                if node_type in IR_DECLARATIONS:
                    ir_counts[node_type] += 1

        for mechanism, pattern, confidence in NAVIGATION_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                navigation_candidates.append(
                    {
                        "source_id": source_id,
                        "line": _line_number(text, match.start()),
                        "mechanism": mechanism,
                        "confidence": confidence,
                        "resolution": "candidate",
                        "evidence": text[match.start() : match.end()][:240],
                    }
                )
        if re.search(r"\b(?:ICommand|RelayCommand|DelegateCommand)\b", text) and re.search(
            r"\b(?:Navigate|ShowViewModel|RequestNavigate)\b", text
        ):
            match = re.search(r"\b(?:Navigate|ShowViewModel|RequestNavigate)\b", text)
            assert match is not None
            navigation_candidates.append(
                {
                    "source_id": source_id,
                    "line": _line_number(text, match.start()),
                    "mechanism": "command-navigation",
                    "confidence": "medium",
                    "resolution": "candidate",
                    "evidence": match.group(0),
                }
            )

    cs_dependency_path = project_output / "dependency" / "cs_dependency.json"
    cs_dependency = read_json(cs_dependency_path) if cs_dependency_path.exists() else {}
    parsed_edges = int(
        cs_dependency.get("dependency_summary", {}).get("total_dependencies", 0)
    )
    duplicate_types = [
        {"type_name": name, "source_ids": sorted(paths), "resolution": "unresolved"}
        for name, paths in sorted(type_definitions.items())
        if len(paths) > 1
    ]
    partial_groups = [
        {"type_name": name, "source_ids": sorted(paths)}
        for name, paths in sorted(partial_definitions.items())
        if paths
    ]
    fallback_unresolved = [
        {
            "kind": "duplicate_type_definition",
            **item,
        }
        for item in duplicate_types
    ]
    graph_partial_groups = cs_dependency.get("partial_groups")
    if isinstance(graph_partial_groups, list):
        partial_groups = graph_partial_groups
    graph_unresolved = cs_dependency.get("unresolved_references")
    unresolved = (
        graph_unresolved
        if isinstance(graph_unresolved, list)
        else fallback_unresolved
    )
    dependency_summary = cs_dependency.get("dependency_summary", {})
    counts = {
        "tree_sitter_roots": tree_roots,
        "tree_sitter_error_nodes": sum(
            item.get("reason") == "tree-sitter ERROR 节点" for item in errors
        ),
        "tree_sitter_missing_nodes": missing_nodes,
        "parser_reported_error_nodes": parser_reported_error_nodes,
        "parser_reported_missing_nodes": parser_reported_missing_nodes,
        "unreported_tree_sitter_diagnostics": max(
            0,
            sum(item.get("reason") == "tree-sitter ERROR 节点" for item in errors)
            + missing_nodes
            - parser_reported_error_nodes
            - parser_reported_missing_nodes,
        ),
        "raw_declarations": dict(sorted(raw_counts.items())),
        "ir_declarations": dict(sorted(ir_counts.items())),
        "partial_type_groups": len(partial_groups),
        "partial_type_files": sum(len(item["source_ids"]) for item in partial_groups),
        "partial_types": partial_groups,
        "duplicate_type_groups": len(duplicate_types),
        "dependency_artifact_exists": int(cs_dependency_path.is_file()),
        "parsed_dependency_edges": parsed_edges,
        "dependency_evidence": int(
            dependency_summary.get("dependency_evidence_count", 0)
        ),
        "candidate_dependency_edges": int(
            dependency_summary.get(
                "candidate_dependency_count", len(duplicate_types)
            )
        ),
        "unresolved_dependencies": len(unresolved),
        "navigation_candidates": len(navigation_candidates),
        "errors": errors,
    }
    return counts, unresolved, navigation_candidates


def _normalize_resource_value(value: str) -> str:
    return value.strip().strip("\"'").replace("\\", "/")


def _resource_source_id(
    project_path: Path, source_xaml: Path, value: str
) -> tuple[str | None, str]:
    normalized = _normalize_resource_value(value)
    lowered = normalized.casefold()
    if lowered.startswith(("http:", "https:", "pack:")):
        return None, "external_or_assembly"
    if ";component/" in lowered:
        return None, "external_or_assembly"
    if normalized.startswith("{") or "{Binding" in normalized:
        return None, "dynamic_or_unsupported"
    candidate = normalized.split("#", 1)[0].split("?", 1)[0]
    if not candidate:
        return None, "unsupported"
    if candidate.startswith("/"):
        resolved = project_path / candidate.lstrip("/")
    else:
        resolved = source_xaml.parent / candidate
    try:
        source_id = repository_relative_id(resolved, project_path)
    except (OSError, ValueError):
        return None, "external_or_assembly"
    return source_id, "internal_path"


def _raw_csproj_declarations(
    project_path: Path, csproj_files: list[Path]
) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    for csproj in csproj_files:
        text, error = _read_text(csproj)
        if text is None:
            declarations.append(
                {
                    "source_csproj": repository_relative_id(csproj, project_path),
                    "classification": "unreadable",
                    "reason": error,
                }
            )
            continue
        try:
            root = ET.fromstring(text.encode("utf-8"), parser=ET.XMLParser(recover=False))
        except Exception as exc:
            declarations.append(
                {
                    "source_csproj": repository_relative_id(csproj, project_path),
                    "classification": "unparseable",
                    "reason": str(exc),
                }
            )
            continue
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            action = _local_name(element.tag)
            if action not in BUILD_ACTIONS:
                continue
            include = element.get("Include") or element.get("Update")
            if not include or "*" in include:
                continue
            normalized = include.replace("\\", "/")
            resolved = csproj.parent / normalized
            try:
                source_id = repository_relative_id(resolved, project_path)
            except ValueError:
                source_id = None
            declarations.append(
                {
                    "source_csproj": repository_relative_id(csproj, project_path),
                    "build_action": action,
                    "path": normalized,
                    "source_id": source_id,
                    "exists": resolved.is_file(),
                }
            )
    return declarations


def _resource_audit(
    project_path: Path,
    project_output: Path,
    xaml_files: list[Path],
    csproj_files: list[Path],
    resource_keys: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repo_resources = discover_project_files(project_path, RESOURCE_EXTENSIONS)
    declarations = _raw_csproj_declarations(project_path, csproj_files)
    declared_ids = {
        str(item["source_id"])
        for item in declarations
        if item.get("source_id")
        and (
            PurePosixPath(str(item["source_id"])).suffix.casefold()
            in RESOURCE_EXTENSIONS
            or item.get("build_action")
            in {"Content", "EmbeddedResource", "Resource", "SplashScreen"}
        )
    }
    parser_resource_path = project_output / "dependency" / "resource_dependency.json"
    parser_resource_data = (
        read_json(parser_resource_path) if parser_resource_path.exists() else {}
    )
    parser_resources = parser_resource_data.get("resources", [])
    parser_closure = parser_resource_data.get("summary", {}).get("closure", {})
    parser_ids = {
        str(item["source_id"])
        for item in parser_resources
        if isinstance(item, dict) and item.get("source_id")
    }

    references: list[dict[str, Any]] = []
    classifications: Counter[str] = Counter()
    for xaml in xaml_files:
        source_id = repository_relative_id(xaml, project_path)
        text, error = _read_text(xaml)
        if text is None:
            continue
        try:
            root = ET.fromstring(text.encode("utf-8"), parser=ET.XMLParser(recover=False))
        except Exception:
            continue
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            attrs = {_local_name(k): v for k, v in element.attrib.items()}
            for attr_name, value in attrs.items():
                for kind in ("StaticResource", "DynamicResource"):
                    for match in re.finditer(
                        r"\{" + kind + r"\s+([^,}\s]+)", value, re.IGNORECASE
                    ):
                        key = match.group(1)
                        if kind == "DynamicResource":
                            classification = "dynamic"
                        elif key in resource_keys:
                            classification = "resolved_internal_key"
                        else:
                            classification = "unsupported_symbolic_reference"
                        classifications[classification] += 1
                        references.append(
                            {
                                "source_id": source_id,
                                "line": getattr(element, "sourceline", None),
                                "attribute": attr_name,
                                "kind": kind,
                                "value": key,
                                "classification": classification,
                                "target_exists": key in resource_keys,
                            }
                        )
                if attr_name not in RESOURCE_ATTRIBUTE_NAMES:
                    continue
                suffix = PurePosixPath(
                    _normalize_resource_value(value).split("?", 1)[0]
                ).suffix.lower()
                if (
                    suffix not in RESOURCE_EXTENSIONS
                    and ";component/" not in value.casefold()
                    and not value.casefold().startswith(("http:", "https:", "pack:"))
                ):
                    continue
                target_id, kind = _resource_source_id(project_path, xaml, value)
                if kind == "external_or_assembly":
                    classification = "external_or_assembly"
                    exists = False
                elif kind != "internal_path" or not target_id:
                    classification = "dynamic_or_unsupported"
                    exists = False
                else:
                    target = project_path.joinpath(*PurePosixPath(target_id).parts)
                    exists = target.is_file()
                    if not exists:
                        classification = "missing_target"
                    elif target_id in declared_ids:
                        classification = "resolved_declared_file"
                    else:
                        classification = "internal_undeclared_file"
                classifications[classification] += 1
                references.append(
                    {
                        "source_id": source_id,
                        "line": getattr(element, "sourceline", None),
                        "attribute": attr_name,
                        "kind": "file_resource",
                        "value": value,
                        "target_source_id": target_id,
                        "classification": classification,
                        "target_exists": exists,
                        "parser_declared": bool(target_id and target_id in parser_ids),
                    }
                )

    parser_linked = int(
        parser_closure.get(
            "xaml_reference_count",
            sum(
                len(item.get("referenced_by_pages", []))
                for item in parser_resources
                if isinstance(item, dict)
            ),
        )
    )
    unresolved = [
        reference
        for reference in references
        if reference["classification"]
        in {
            "missing_target",
            "unsupported_symbolic_reference",
            "dynamic_or_unsupported",
        }
    ]
    metrics = {
        "dependency_artifact_exists": int(parser_resource_path.is_file()),
        "repository_resource_files": len(repo_resources),
        "repository_resource_source_ids": [
            repository_relative_id(path, project_path) for path in repo_resources
        ],
        "csproj_files": len(csproj_files),
        "raw_csproj_declarations": len(declarations),
        "declared_resource_source_ids": len(declared_ids),
        "parser_resource_source_ids": len(parser_ids),
        "xaml_direct_references": len(references),
        "xaml_file_references": sum(
            item.get("kind") == "file_resource" for item in references
        ),
        "xaml_symbolic_references": sum(
            item.get("kind") in {"StaticResource", "DynamicResource"}
            for item in references
        ),
        "audit_classified_references": sum(classifications.values()),
        "parser_linked_references": parser_linked,
        "parser_resolved_references": int(
            parser_closure.get("resolved_reference_count", 0)
        ),
        "parser_unexplained_references": int(
            parser_closure.get("unexplained_reference_count", 0)
        ),
        "classification": dict(sorted(classifications.items())),
        "resolved_references": sum(
            classifications[key]
            for key in (
                "resolved_declared_file",
                "internal_undeclared_file",
                "resolved_internal_key",
            )
        ),
        "target_exists": sum(bool(item.get("target_exists")) for item in references),
        "target_missing": classifications["missing_target"],
        "external_references": classifications["external_or_assembly"],
        "dynamic_or_unsupported_references": (
            classifications["dynamic"]
            + classifications["dynamic_or_unsupported"]
            + classifications["unsupported_symbolic_reference"]
        ),
        "unexplained_references": len(references) - sum(classifications.values()),
        "project_file_missing": not csproj_files,
        "declarations": declarations,
        "references": references,
    }
    return metrics, unresolved


def _file_inventory(project_path: Path) -> tuple[list[Path], list[Path], list[Path], dict[str, Any]]:
    all_cs = discover_project_files(project_path, [".cs"])
    xaml = discover_project_files(project_path, [".xaml"])
    csproj = discover_project_files(project_path, [".csproj"])
    filtered: Counter[str] = Counter()
    cs: list[Path] = []
    for path in all_cs:
        if path.name.endswith(".Designer.cs"):
            filtered["designer_cs"] += 1
        elif path.name == "AssemblyInfo.cs":
            filtered["assembly_info_cs"] += 1
        else:
            cs.append(path)

    # 补充统计物理存在但被路径发现规则有意排除的源码文件。
    for path in project_path.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in {".cs", ".xaml", ".csproj"}:
            continue
        if path in all_cs or path in xaml or path in csproj:
            continue
        if path.is_symlink():
            filtered["symlink"] += 1
        elif is_ignored_source_path(path, project_path):
            ignored_parts = [
                part.casefold()
                for part in path.relative_to(project_path).parts[:-1]
                if part.casefold() in IGNORED_SOURCE_DIRECTORIES
            ]
            reason = f"ignored_directory:{ignored_parts[0]}" if ignored_parts else "outside_repository"
            filtered[reason] += 1
        else:
            filtered["other"] += 1
    return cs, xaml, csproj, {"count": sum(filtered.values()), "reasons": dict(sorted(filtered.items()))}


def _artifact_inventory(
    project_path: Path,
    project_output: Path,
    cs: list[Path],
    xaml: list[Path],
    csproj: list[Path],
    filtered: dict[str, Any],
) -> dict[str, Any]:
    expected: list[tuple[str, Path]] = []
    unreadable: list[dict[str, str]] = []
    for source in [*cs, *xaml, *csproj]:
        source_id = repository_relative_id(source, project_path)
        subdir = "cs" if source.suffix.casefold() == ".cs" else "xaml"
        expected.append((source_id, mirrored_json_path(project_output / subdir, source_id)))
        try:
            source.read_bytes()
        except OSError as exc:
            unreadable.append({"source_id": source_id, "reason": str(exc)})

    source_ids = [source_id for source_id, _ in expected]
    output_paths = [path.relative_to(project_output).as_posix() for _, path in expected]
    missing = [
        {"source_id": source_id, "expected_artifact": path.relative_to(project_output).as_posix()}
        for source_id, path in expected
        if not path.is_file()
    ]

    def successful_for(sources: list[Path], subdir: str) -> int:
        return sum(
            mirrored_json_path(
                project_output / subdir,
                repository_relative_id(source, project_path),
            ).is_file()
            for source in sources
        )

    invalid_artifacts: list[dict[str, str]] = []
    actual_ids: list[str] = []
    for directory in (project_output / "cs", project_output / "xaml"):
        if not directory.exists():
            continue
        for artifact in sorted(directory.rglob("*.json")):
            try:
                actual_ids.append(artifact_source_id(read_json(artifact), artifact))
            except Exception as exc:
                invalid_artifacts.append(
                    {
                        "artifact": artifact.relative_to(project_output).as_posix(),
                        "reason": str(exc),
                    }
                )
    duplicate_ids = sorted(
        source_id for source_id, count in Counter(actual_ids).items() if count > 1
    )
    output_collisions = sorted(
        path for path, count in Counter(output_paths).items() if count > 1
    )
    return {
        "eligible_source_files": len(expected),
        "eligible_cs_files": len(cs),
        "eligible_xaml_files": len(xaml),
        "eligible_csproj_files": len(csproj),
        "successful_artifacts": len(expected) - len(missing),
        "successful_cs_artifacts": successful_for(cs, "cs"),
        "successful_xaml_artifacts": successful_for(xaml, "xaml"),
        "successful_csproj_artifacts": successful_for(csproj, "xaml"),
        "unique_source_ids": len(set(source_ids)),
        "unique_output_paths": len(set(output_paths)),
        "missing_artifacts": len(missing),
        "duplicate_source_ids": len(duplicate_ids),
        "output_collisions": len(output_collisions),
        "unreadable_files": len(unreadable),
        "intentionally_filtered": filtered,
        "missing": missing,
        "duplicates": duplicate_ids,
        "collisions": output_collisions,
        "unreadable": unreadable,
        "invalid_artifacts": invalid_artifacts,
        "source_ids": sorted(source_ids),
        "artifact_paths": sorted(output_paths),
    }


def _page_dependency_audit(
    project_output: Path,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    path = project_output / "dependency" / "page_dependency.json"
    data = read_json(path) if path.exists() else {}
    pages = data.get("pages", {})
    certain_edges = sum(len(page.get("dependencies", [])) for page in pages.values())
    ambiguous = data.get("ambiguous_references", {})
    parser_candidates = data.get("candidate_edges", [])
    unsupported = data.get("unsupported_references", [])
    unresolved = [
        {"source_page_id": page_id, **item}
        for page_id, items in sorted(ambiguous.items())
        for item in items
    ]
    return (
        {
            "dependency_artifact_exists": int(path.is_file()),
            "pages": len(pages),
            "certain_edges": certain_edges,
            "certain_edge_evidence": int(
                data.get("dependency_summary", {}).get(
                    "dependency_evidence_count", 0
                )
            ),
            "current_unresolved_edges": len(unresolved),
            "parser_candidate_edges": len(parser_candidates),
            "parser_unsupported_references": len(unsupported),
            "cycle_groups": len(data.get("cycle_groups", [])),
            "migration_order_entries": len(data.get("migration_order", [])),
        },
        unresolved,
        unsupported,
    )


def _indirect_resource_audit(project_output: Path) -> dict[str, Any]:
    """检查间接资源阶段约定的三个确定性产物。"""
    dependency_dir = project_output / "dependency"
    expected = (
        "indirect_resources.json",
        "data_resources.json",
        "template_resources.json",
    )
    available = [name for name in expected if (dependency_dir / name).is_file()]
    return {
        "expected_artifacts": len(expected),
        "available_artifacts": len(available),
        "missing_artifacts": sorted(set(expected) - set(available)),
    }


def _rate_from_components(
    parser_id: str,
    components: dict[str, dict[str, int]],
    *,
    threshold: float = PARSER_RATE_THRESHOLD,
) -> dict[str, Any]:
    """用可审计的已处理单位/应处理单位计算单阶段解析率。"""
    normalized: dict[str, dict[str, int]] = {}
    handled_units = 0
    total_units = 0
    for name, values in sorted(components.items()):
        total = max(0, int(values.get("total", 0)))
        handled = min(total, max(0, int(values.get("handled", 0))))
        normalized[name] = {"handled": handled, "total": total}
        handled_units += handled
        total_units += total
    rate = handled_units / total_units if total_units else 1.0
    definition = PARSER_RATE_DEFINITIONS[parser_id]
    return {
        "parser_id": parser_id,
        "label": definition["label"],
        "basis": definition["basis"],
        "handled_units": handled_units,
        "total_units": total_units,
        "rate": round(rate, 6),
        "percentage": round(rate * 100, 2),
        "threshold": threshold,
        "passed": rate + 1e-12 >= threshold,
        "components": normalized,
    }


def _rate_summary(
    parsers: dict[str, dict[str, Any]],
    *,
    threshold: float = PARSER_RATE_THRESHOLD,
) -> dict[str, Any]:
    """按解析器等权宏平均，避免大型 XAML 项目淹没较小阶段。"""
    rates = [float(item["rate"]) for item in parsers.values()]
    macro_rate = sum(rates) / len(rates) if rates else 1.0
    below = sorted(
        parser_id for parser_id, item in parsers.items() if not item["passed"]
    )
    return {
        "threshold": threshold,
        "aggregation": "macro-average-across-parsers",
        "parser_count": len(parsers),
        "rate": round(macro_rate, 6),
        "percentage": round(macro_rate * 100, 2),
        "all_parsers_passed": not below,
        "below_threshold": below,
        "passed": macro_rate + 1e-12 >= threshold and not below,
    }


def _project_parser_rates(
    files: dict[str, Any],
    xaml: dict[str, Any],
    csharp: dict[str, Any],
    resources: dict[str, Any],
    pages: dict[str, Any],
    indirect_resources: dict[str, Any],
    *,
    threshold: float = PARSER_RATE_THRESHOLD,
) -> dict[str, Any]:
    """把七阶段结果转换为逐项目解析率。"""
    raw_declarations = sum(int(value) for value in csharp["raw_declarations"].values())
    retained_declarations = sum(
        min(int(raw), int(csharp["ir_declarations"].get(kind, 0)))
        for kind, raw in csharp["raw_declarations"].items()
    )
    diagnostics = int(csharp["tree_sitter_error_nodes"]) + int(
        csharp["tree_sitter_missing_nodes"]
    )
    reported_diagnostics = min(
        diagnostics,
        int(csharp["parser_reported_error_nodes"])
        + int(csharp["parser_reported_missing_nodes"]),
    )

    semantic_pairs = {
        "binding": "binding",
        "multibinding": "multibinding",
        "prioritybinding": "prioritybinding",
        "command": "command",
        "command_parameter": "command_parameter",
        "event_handler": "event_handler",
        "static_resource": "static_resource",
        "dynamic_resource": "dynamic_resource",
        "file_resource_reference": "file_resource",
    }
    semantic_total = sum(
        int(xaml["occurrences"].get(occurrence, 0))
        for occurrence in semantic_pairs
    )
    semantic_handled = sum(
        min(
            int(xaml["occurrences"].get(occurrence, 0)),
            int(xaml["structured_extractions"].get(structured, 0)),
        )
        for occurrence, structured in semantic_pairs.items()
    )

    candidates = int(csharp["candidate_dependency_edges"])
    page_navigation_candidates = int(pages["audit_navigation_candidates"])
    parser_navigation_records = int(pages["parser_candidate_edges"]) + int(
        pages["parser_unsupported_references"]
    )
    parser_resource_links = max(
        0,
        int(resources["parser_linked_references"])
        - int(resources["parser_unexplained_references"]),
    )

    parsers = {
        "cs_parser": _rate_from_components(
            "cs_parser",
            {
                "source_files": {
                    "handled": files["successful_cs_artifacts"],
                    "total": files["eligible_cs_files"],
                },
                "required_declarations": {
                    "handled": retained_declarations,
                    "total": raw_declarations,
                },
                "reported_diagnostics": {
                    "handled": reported_diagnostics,
                    "total": diagnostics,
                },
            },
            threshold=threshold,
        ),
        "xaml_parser": _rate_from_components(
            "xaml_parser",
            {
                "source_files": {
                    "handled": files["successful_xaml_artifacts"]
                    + files["successful_csproj_artifacts"],
                    "total": files["eligible_xaml_files"]
                    + files["eligible_csproj_files"],
                },
                "xml_elements": {
                    "handled": min(
                        xaml["raw_xml_elements"], xaml["xaml_ir_nodes"]
                    ),
                    "total": xaml["raw_xml_elements"],
                },
                "required_semantics": {
                    "handled": semantic_handled,
                    "total": semantic_total,
                },
            },
            threshold=threshold,
        ),
        "cs_dependency": _rate_from_components(
            "cs_dependency",
            {
                "output_artifact": {
                    "handled": csharp["dependency_artifact_exists"],
                    "total": 1,
                },
                "certain_edges_with_evidence": {
                    "handled": min(
                        csharp["parsed_dependency_edges"],
                        csharp["dependency_evidence"],
                    ),
                    "total": csharp["parsed_dependency_edges"],
                },
                "candidate_edges_explicit": {
                    "handled": min(candidates, csharp["unresolved_dependencies"]),
                    "total": candidates,
                },
            },
            threshold=threshold,
        ),
        "indirect_resource_dependency": _rate_from_components(
            "indirect_resource_dependency",
            {
                "output_artifacts": {
                    "handled": indirect_resources["available_artifacts"],
                    "total": indirect_resources["expected_artifacts"],
                }
            },
            threshold=threshold,
        ),
        "page_dependency": _rate_from_components(
            "page_dependency",
            {
                "output_artifact": {
                    "handled": pages["dependency_artifact_exists"],
                    "total": 1,
                },
                "pages_in_migration_order": {
                    "handled": min(
                        pages["pages"], pages["migration_order_entries"]
                    ),
                    "total": pages["pages"],
                },
                "certain_edges_with_evidence": {
                    "handled": min(
                        pages["certain_edges"], pages["certain_edge_evidence"]
                    ),
                    "total": pages["certain_edges"],
                },
                "navigation_candidates_classified": {
                    "handled": min(
                        page_navigation_candidates, parser_navigation_records
                    ),
                    "total": page_navigation_candidates,
                },
                "ambiguous_edges_explicit": {
                    "handled": pages["current_unresolved_edges"],
                    "total": pages["current_unresolved_edges"],
                },
            },
            threshold=threshold,
        ),
        "resource_dependency": _rate_from_components(
            "resource_dependency",
            {
                "output_artifact": {
                    "handled": resources["dependency_artifact_exists"],
                    "total": 1,
                },
                "repository_resources_in_inventory": {
                    "handled": min(
                        resources["repository_resource_files"],
                        resources["parser_resource_source_ids"],
                    ),
                    "total": resources["repository_resource_files"],
                },
                "xaml_references_classified": {
                    "handled": min(
                        resources["xaml_direct_references"], parser_resource_links
                    ),
                    "total": resources["xaml_direct_references"],
                },
            },
            threshold=threshold,
        ),
        "control_dependency": _rate_from_components(
            "control_dependency",
            {
                "page_artifacts": {
                    "handled": xaml["control_artifacts"],
                    "total": xaml["page_xaml_files"],
                },
                "visual_nodes_preserved": {
                    "handled": min(
                        xaml["page_visual_nodes"],
                        xaml["migration_preserved_visual_nodes"],
                    ),
                    "total": xaml["page_visual_nodes"],
                },
            },
            threshold=threshold,
        ),
    }
    return {
        "threshold": threshold,
        "parsers": parsers,
        "overall": _rate_summary(parsers, threshold=threshold),
    }


def _aggregate_parser_rates(
    reports: list[dict[str, Any]],
    *,
    threshold: float = PARSER_RATE_THRESHOLD,
) -> dict[str, Any]:
    parsers: dict[str, dict[str, Any]] = {}
    for parser_id in PARSER_RATE_DEFINITIONS:
        components: defaultdict[str, dict[str, int]] = defaultdict(
            lambda: {"handled": 0, "total": 0}
        )
        for report in reports:
            parser = report["parser_rates"]["parsers"][parser_id]
            for component, values in parser["components"].items():
                components[component]["handled"] += int(values["handled"])
                components[component]["total"] += int(values["total"])
        parsers[parser_id] = _rate_from_components(
            parser_id, dict(components), threshold=threshold
        )
    return {
        "threshold": threshold,
        "parsers": parsers,
        "overall": _rate_summary(parsers, threshold=threshold),
    }


def _loss_assessment(
    files: dict[str, Any],
    xaml: dict[str, Any],
    csharp: dict[str, Any],
    resources: dict[str, Any],
    unresolved_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    known: list[dict[str, Any]] = []
    potential: list[dict[str, Any]] = []
    if files["missing_artifacts"] or files["output_collisions"] or files["duplicate_source_ids"]:
        known.append({"mechanism": "file_identity", "count": files["missing_artifacts"] + files["output_collisions"] + files["duplicate_source_ids"]})
    if xaml["raw_xml_elements"] != xaml["xaml_ir_nodes"]:
        known.append({"mechanism": "xaml_structure", "raw": xaml["raw_xml_elements"], "ir": xaml["xaml_ir_nodes"]})
    if xaml["page_custom_controls"] > xaml["migration_custom_control_nodes"]:
        known.append(
            {
                "mechanism": "custom_controls_dropped_from_migration_tree",
                "page_custom_controls": xaml["page_custom_controls"],
                "migration_ir": xaml["migration_custom_control_nodes"],
            }
        )
    if xaml["migration_dropped_visual_nodes"]:
        known.append(
            {
                "mechanism": "classified_visual_nodes_dropped_from_migration_tree",
                "page_visual_nodes": xaml["page_visual_nodes"],
                "migration_ir": xaml["migration_control_ir_nodes"],
                "dropped": xaml["migration_dropped_visual_nodes"],
            }
        )
    for kind in ("binding", "multibinding", "prioritybinding", "command", "command_parameter", "event_handler", "static_resource", "dynamic_resource"):
        occurrence = xaml["occurrences"].get(kind, 0)
        extracted = xaml["structured_extractions"].get(kind, 0)
        if occurrence > extracted:
            known.append({"mechanism": f"unstructured_xaml_{kind}", "occurrences": occurrence, "structured": extracted})
    for kind, raw_count in csharp["raw_declarations"].items():
        ir_count = csharp["ir_declarations"].get(kind, 0)
        if raw_count > ir_count:
            known.append({"mechanism": f"csharp_{kind}_declaration_loss", "raw": raw_count, "ir": ir_count})
    if resources["xaml_file_references"] > resources["parser_linked_references"]:
        known.append(
            {
                "mechanism": "resource_reference_not_linked_by_parser",
                "xaml_file_references": resources["xaml_file_references"],
                "parser_links": resources["parser_linked_references"],
            }
        )
    if csharp["parsed_dependency_edges"] > csharp["dependency_evidence"]:
        known.append(
            {
                "mechanism": "csharp_dependency_without_evidence",
                "dependencies": csharp["parsed_dependency_edges"],
                "evidence": csharp["dependency_evidence"],
            }
        )
    if csharp["tree_sitter_error_nodes"] or csharp["tree_sitter_missing_nodes"]:
        potential.append({"mechanism": "tree_sitter_error_or_missing", "count": csharp["tree_sitter_error_nodes"] + csharp["tree_sitter_missing_nodes"]})
    if xaml["unsupported_nodes"]:
        potential.append({"mechanism": "unsupported_xaml_nodes", "count": xaml["unsupported_nodes"]})
    if resources["dynamic_or_unsupported_references"] or resources["target_missing"]:
        potential.append({"mechanism": "unresolved_resources", "count": resources["dynamic_or_unsupported_references"] + resources["target_missing"]})
    if unresolved_count:
        potential.append({"mechanism": "unresolved_dependencies", "count": unresolved_count})
    if files["missing_artifacts"] or files["output_collisions"] or csharp["tree_sitter_error_nodes"]:
        impact = "高"
    elif known or resources["target_missing"] or unresolved_count:
        impact = "中"
    else:
        impact = "低"
    return known, potential, impact


def audit_project(
    candidate: dict[str, Any],
    *,
    repos_root: Path,
    parse_root: Path,
) -> dict[str, Any]:
    project_name = str(candidate["local_dir"])
    project_path = repos_root / project_name
    project_output = parse_root / project_name
    actual_sha = subprocess.run(
        ["git", "-C", str(project_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual_sha != candidate["commit_sha"]:
        raise RuntimeError(
            f"{project_name} 固定提交不一致: {actual_sha} != {candidate['commit_sha']}"
        )
    cs, xaml, csproj, filtered = _file_inventory(project_path)
    files = _artifact_inventory(project_path, project_output, cs, xaml, csproj, filtered)
    (
        xaml_metrics,
        xaml_special_nodes,
        resource_keys,
        xaml_navigation_candidates,
    ) = _xaml_audit(
        project_path, project_output, xaml
    )
    csharp_metrics, csharp_unresolved, navigation_candidates = _csharp_audit(
        project_path, project_output, cs
    )
    resource_metrics, resource_unresolved = _resource_audit(
        project_path, project_output, xaml, csproj, resource_keys
    )
    page_metrics, page_unresolved, page_unsupported = _page_dependency_audit(
        project_output
    )
    indirect_resource_metrics = _indirect_resource_audit(project_output)
    page_metrics = {
        **page_metrics,
        "audit_navigation_candidates": len(navigation_candidates)
        + len(xaml_navigation_candidates),
    }
    unresolved = [
        *csharp_unresolved,
        *resource_unresolved,
        *page_unresolved,
        *navigation_candidates,
        *xaml_navigation_candidates,
    ]
    known, potential, impact = _loss_assessment(
        files, xaml_metrics, csharp_metrics, resource_metrics, len(unresolved)
    )
    run_summary_path = project_output / "run_summary.json"
    run_summary = read_json(run_summary_path) if run_summary_path.exists() else {}
    unsupported_xaml = [
        item
        for item in xaml_special_nodes
        if item["classification"] == "unsupported_node"
    ]
    unsupported_resources = [
        item
        for item in resource_metrics["references"]
        if item["classification"]
        in {"unsupported_symbolic_reference", "dynamic_or_unsupported"}
    ]
    parser_rates = _project_parser_rates(
        files,
        xaml_metrics,
        csharp_metrics,
        resource_metrics,
        page_metrics,
        indirect_resource_metrics,
    )
    return {
        "schema_version": 2,
        "id_scheme": SOURCE_ID_SCHEME,
        "project": project_name,
        "status": candidate["status"],
        "commit_sha": actual_sha,
        "target_paths": list(candidate.get("target_paths", [])),
        "pipeline": {
            "success": bool(run_summary.get("pipeline_success")),
            "failed_steps": run_summary.get("failed_steps", []),
        },
        "files": files,
        "xaml": xaml_metrics,
        "csharp": csharp_metrics,
        "indirect_resources": indirect_resource_metrics,
        "resources": resource_metrics,
        "pages": page_metrics,
        "parser_rates": parser_rates,
        "unsupported": {
            "xaml_nodes": unsupported_xaml,
            "resource_references": unsupported_resources,
            "page_references": page_unsupported,
            "count": len(unsupported_xaml)
            + len(unsupported_resources)
            + len(page_unsupported),
        },
        "classified_node_inventory": {
            "custom_controls": [
                item
                for item in xaml_special_nodes
                if item["classification"] == "custom_control"
            ],
            "unsupported_nodes": [
                item
                for item in xaml_special_nodes
                if item["classification"] == "unsupported_node"
            ],
        },
        "unresolved": unresolved,
        "unresolved_count": len(unresolved),
        "known_information_loss": known,
        "potential_information_loss": potential,
        "migration_impact": impact,
    }


def _sum_path(reports: Iterable[dict[str, Any]], *path: str) -> int:
    total = 0
    for report in reports:
        value: Any = report
        for key in path:
            value = value.get(key, 0) if isinstance(value, dict) else 0
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += int(value)
    return total


def _aggregate(reports: list[dict[str, Any]]) -> dict[str, Any]:
    classification = Counter()
    xaml_occurrences = Counter()
    structured = Counter()
    raw_cs = Counter()
    ir_cs = Counter()
    resource_classification = Counter()
    for report in reports:
        classification.update(report["xaml"]["classification"])
        xaml_occurrences.update(report["xaml"]["occurrences"])
        structured.update(report["xaml"]["structured_extractions"])
        raw_cs.update(report["csharp"]["raw_declarations"])
        ir_cs.update(report["csharp"]["ir_declarations"])
        resource_classification.update(report["resources"]["classification"])
    aggregate = {
        "project_count": len(reports),
        "pipeline_success_count": sum(report["pipeline"]["success"] for report in reports),
        "files": {
            key: _sum_path(reports, "files", key)
            for key in (
                "eligible_source_files",
                "eligible_cs_files",
                "eligible_xaml_files",
                "eligible_csproj_files",
                "successful_artifacts",
                "successful_cs_artifacts",
                "successful_xaml_artifacts",
                "successful_csproj_artifacts",
                "unique_source_ids",
                "unique_output_paths",
                "missing_artifacts",
                "duplicate_source_ids",
                "output_collisions",
                "unreadable_files",
            )
        },
        "xaml": {
            "raw_xml_elements": _sum_path(reports, "xaml", "raw_xml_elements"),
            "xaml_ir_nodes": _sum_path(reports, "xaml", "xaml_ir_nodes"),
            "classification": dict(sorted(classification.items())),
            "silently_unclassified_nodes": _sum_path(reports, "xaml", "silently_unclassified_nodes"),
            "page_visual_nodes": _sum_path(reports, "xaml", "page_visual_nodes"),
            "page_xaml_files": _sum_path(reports, "xaml", "page_xaml_files"),
            "control_artifacts": _sum_path(reports, "xaml", "control_artifacts"),
            "migration_control_ir_nodes": _sum_path(reports, "xaml", "migration_control_ir_nodes"),
            "migration_preserved_visual_nodes": _sum_path(reports, "xaml", "migration_preserved_visual_nodes"),
            "migration_custom_control_nodes": _sum_path(reports, "xaml", "migration_custom_control_nodes"),
            "migration_dropped_visual_nodes": _sum_path(reports, "xaml", "migration_dropped_visual_nodes"),
            "occurrences": dict(sorted(xaml_occurrences.items())),
            "structured_extractions": dict(sorted(structured.items())),
        },
        "csharp": {
            "tree_sitter_roots": _sum_path(reports, "csharp", "tree_sitter_roots"),
            "tree_sitter_error_nodes": _sum_path(reports, "csharp", "tree_sitter_error_nodes"),
            "tree_sitter_missing_nodes": _sum_path(reports, "csharp", "tree_sitter_missing_nodes"),
            "parser_reported_error_nodes": _sum_path(reports, "csharp", "parser_reported_error_nodes"),
            "parser_reported_missing_nodes": _sum_path(reports, "csharp", "parser_reported_missing_nodes"),
            "unreported_tree_sitter_diagnostics": _sum_path(reports, "csharp", "unreported_tree_sitter_diagnostics"),
            "raw_declarations": dict(sorted(raw_cs.items())),
            "ir_declarations": dict(sorted(ir_cs.items())),
            "declaration_gap_total": sum(
                max(0, raw_cs[kind] - ir_cs[kind])
                for kind in set(raw_cs) | set(ir_cs)
            ),
            "partial_type_groups": _sum_path(reports, "csharp", "partial_type_groups"),
            "partial_type_files": _sum_path(reports, "csharp", "partial_type_files"),
            "dependency_artifact_exists": _sum_path(reports, "csharp", "dependency_artifact_exists"),
            "parsed_dependency_edges": _sum_path(reports, "csharp", "parsed_dependency_edges"),
            "dependency_evidence": _sum_path(reports, "csharp", "dependency_evidence"),
            "candidate_dependency_edges": _sum_path(reports, "csharp", "candidate_dependency_edges"),
            "unresolved_dependencies": _sum_path(reports, "csharp", "unresolved_dependencies"),
        },
        "resources": {
            key: _sum_path(reports, "resources", key)
            for key in (
                "repository_resource_files",
                "dependency_artifact_exists",
                "declared_resource_source_ids",
                "parser_resource_source_ids",
                "xaml_direct_references",
                "xaml_file_references",
                "xaml_symbolic_references",
                "resolved_references",
                "target_exists",
                "target_missing",
                "external_references",
                "dynamic_or_unsupported_references",
                "unexplained_references",
                "parser_linked_references",
                "parser_resolved_references",
                "parser_unexplained_references",
            )
        }
        | {"classification": dict(sorted(resource_classification.items()))},
        "pages": {
            "dependency_artifact_exists": _sum_path(reports, "pages", "dependency_artifact_exists"),
            "pages": _sum_path(reports, "pages", "pages"),
            "certain_edges": _sum_path(reports, "pages", "certain_edges"),
            "certain_edge_evidence": _sum_path(reports, "pages", "certain_edge_evidence"),
            "navigation_candidates": _sum_path(reports, "pages", "audit_navigation_candidates"),
            "parser_candidate_edges": _sum_path(reports, "pages", "parser_candidate_edges"),
            "parser_unsupported_references": _sum_path(reports, "pages", "parser_unsupported_references"),
            "current_unresolved_edges": _sum_path(reports, "pages", "current_unresolved_edges"),
            "cycle_groups": _sum_path(reports, "pages", "cycle_groups"),
            "migration_order_entries": _sum_path(reports, "pages", "migration_order_entries"),
        },
        "indirect_resources": {
            "expected_artifacts": _sum_path(
                reports, "indirect_resources", "expected_artifacts"
            ),
            "available_artifacts": _sum_path(
                reports, "indirect_resources", "available_artifacts"
            ),
        },
        "unsupported_count": sum(report["unsupported"]["count"] for report in reports),
        "unresolved_count": sum(report["unresolved_count"] for report in reports),
        "impact_distribution": dict(sorted(Counter(report["migration_impact"] for report in reports).items())),
    }
    aggregate["parser_rates"] = _aggregate_parser_rates(reports)
    return aggregate


def _render_parser_rate_report(
    reports: list[dict[str, Any]], aggregate: dict[str, Any]
) -> str:
    rates = aggregate["parser_rates"]
    overall = rates["overall"]
    lines = [
        "# 阶段一分解析器解析率报告",
        "",
        f"通过阈值固定为 {rates['threshold'] * 100:.0f}%。总体采用七个解析器等权宏平均，并要求每个解析器均达到阈值；当前总体解析率为 {overall['percentage']:.2f}%，结论为{'通过' if overall['passed'] else '不通过'}。",
        "",
        "解析率衡量的是应处理单位是否已有产物、结构化结果、证据或显式 unsupported/unresolved 分类。显式标记为暂不支持仍算作已处理，但不等于语义正确率、精确率或召回率，也不代表能够达到 100% 解析。",
        "",
        "## 聚合解析率",
        "",
        "| 解析器 | 统计口径 | 已处理单位 | 应处理单位 | 解析率 | 结论 |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for parser_id in PARSER_RATE_DEFINITIONS:
        item = rates["parsers"][parser_id]
        lines.append(
            f"| {item['label']} | {item['basis']} | {item['handled_units']} | "
            f"{item['total_units']} | {item['percentage']:.2f}% | "
            f"{'通过' if item['passed'] else '不通过'} |"
        )

    parser_ids = list(PARSER_RATE_DEFINITIONS)
    lines.extend(
        [
            "",
            "## 逐项目解析率",
            "",
            "| 项目 | C# | XAML | C# 依赖 | 间接资源 | 页面依赖 | 静态资源 | 控件依赖 | 总体 | 结论 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for report in reports:
        project_rates = report["parser_rates"]
        values = [
            f"{project_rates['parsers'][parser_id]['percentage']:.2f}%"
            for parser_id in parser_ids
        ]
        project_overall = project_rates["overall"]
        lines.append(
            "| "
            + " | ".join(
                [
                    report["project"],
                    *values,
                    f"{project_overall['percentage']:.2f}%",
                    "通过" if project_overall["passed"] else "不通过",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 口径边界",
            "",
            "- C# 结构率只覆盖研究任务约定的 namespace、类型、字段、属性、方法、构造函数和事件，不把所有词法节点都纳入分母。",
            "- XAML 语义率只覆盖当前审计规则能够独立计数的 Binding、Command、事件和资源引用；规则本身的漏检不由该比例证明。",
            "- 依赖阶段把有证据的确定边和显式 candidate、unsupported、unresolved 都视为已处理；该指标不验证每条边的人工语义 GT。",
            "- 资源阶段把存在、缺失、外部、动态和暂不支持等明确分类都视为已处理；“已分类”不等于“目标可迁移”。",
            "- 控件阶段要求视觉节点进入基础控件树或独立分类清单，不要求所有节点都能直接生成 React 组件。",
            "",
        ]
    )
    return "\n".join(lines)


def _render_report(reports: list[dict[str, Any]], aggregate: dict[str, Any]) -> str:
    parser_rates = aggregate["parser_rates"]
    rate_lines = [
        f"- 分解析器解析率：总体 {parser_rates['overall']['percentage']:.2f}%（阈值 {parser_rates['threshold'] * 100:.0f}%），{'通过' if parser_rates['overall']['passed'] else '不通过'}；低于阈值的解析器：{('、'.join(parser_rates['overall']['below_threshold']) or '无')}。",
        "",
        "### 分解析器解析率",
        "",
        "| 解析器 | 已处理/应处理 | 解析率 | 结论 |",
        "| --- | ---: | ---: | --- |",
    ]
    for parser_id in PARSER_RATE_DEFINITIONS:
        item = parser_rates["parsers"][parser_id]
        rate_lines.append(
            f"| {item['label']} | {item['handled_units']}/{item['total_units']} | "
            f"{item['percentage']:.2f}% | {'通过' if item['passed'] else '不通过'} |"
        )
    rate_lines.append("")
    lines = [
        "# 阶段一解析完整性审计报告",
        "",
        "本报告区分工程执行成功、文件级覆盖、结构覆盖、语义引用覆盖和资源闭包。没有人工 GT 的项目不能据此宣称绝对完整。",
        "",
        "## 聚合结果",
        "",
        f"- 工程执行：{aggregate['pipeline_success_count']}/{aggregate['project_count']} 个项目七阶段无异常。",
        f"- 文件覆盖：{aggregate['files']['successful_artifacts']}/{aggregate['files']['eligible_source_files']} 个纳入范围的 C#/XAML/csproj 文件有预期产物；缺失 {aggregate['files']['missing_artifacts']}，输出覆盖 {aggregate['files']['output_collisions']}。",
        f"- XAML 结构：原始元素 {aggregate['xaml']['raw_xml_elements']}，完整 IR 节点 {aggregate['xaml']['xaml_ir_nodes']}，静默未分类 {aggregate['xaml']['silently_unclassified_nodes']}。",
        f"- XAML 迁移清单：页面视觉节点 {aggregate['xaml']['page_visual_nodes']}，基础控件树节点 {aggregate['xaml']['migration_control_ir_nodes']}，独立自定义控件 {aggregate['xaml']['migration_custom_control_nodes']}，静默视觉差额 {aggregate['xaml']['migration_dropped_visual_nodes']}。",
        f"- XAML 语义：Binding {aggregate['xaml']['structured_extractions'].get('binding', 0)}，Command {aggregate['xaml']['structured_extractions'].get('command', 0)}，事件 {aggregate['xaml']['structured_extractions'].get('event_handler', 0)}，StaticResource {aggregate['xaml']['structured_extractions'].get('static_resource', 0)}。",
        f"- C# 结构：tree-sitter 根 {aggregate['csharp']['tree_sitter_roots']}，ERROR 节点 {aggregate['csharp']['tree_sitter_error_nodes']}，缺失节点 {aggregate['csharp']['tree_sitter_missing_nodes']}，解析器未报告诊断 {aggregate['csharp']['unreported_tree_sitter_diagnostics']}，声明差额 {aggregate['csharp']['declaration_gap_total']}。",
        f"- C# 关联：确定依赖 {aggregate['csharp']['parsed_dependency_edges']}，证据 {aggregate['csharp']['dependency_evidence']}，按完整名称确认 partial 组 {aggregate['csharp']['partial_type_groups']}，候选依赖 {aggregate['csharp']['candidate_dependency_edges']}，unresolved 依赖 {aggregate['csharp']['unresolved_dependencies']}。",
        f"- 资源闭包：仓库资源文件 {aggregate['resources']['repository_resource_files']}，解析器资源 ID {aggregate['resources']['parser_resource_source_ids']}，XAML 引用 {aggregate['resources']['xaml_direct_references']}，解析器显式链接 {aggregate['resources']['parser_linked_references']}，解析器未解释 {aggregate['resources']['parser_unexplained_references']}。",
        f"- 页面依赖：当前确定边 {aggregate['pages']['certain_edges']}，确定边证据 {aggregate['pages']['certain_edge_evidence']}，审计候选 {aggregate['pages']['navigation_candidates']}，解析器候选 {aggregate['pages']['parser_candidate_edges']}，解析器暂不支持 {aggregate['pages']['parser_unsupported_references']}，当前歧义边 {aggregate['pages']['current_unresolved_edges']}。",
        f"- unsupported 项 {aggregate['unsupported_count']}，unresolved 项 {aggregate['unresolved_count']}。",
        "",
        *rate_lines,
        "## 逐项目结果",
        "",
        "| 项目 | 状态 | 工程执行 | 文件产物 | XAML 原始/IR | C# ERROR | 资源引用/解析器链接 | unresolved | 迁移影响 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for report in reports:
        lines.append(
            "| {project} | {status} | {pipeline} | {artifacts}/{eligible} | {raw}/{ir} | {errors} | {refs}/{links} | {unresolved} | {impact} |".format(
                project=report["project"],
                status=report["status"],
                pipeline="通过" if report["pipeline"]["success"] else "失败",
                artifacts=report["files"]["successful_artifacts"],
                eligible=report["files"]["eligible_source_files"],
                raw=report["xaml"]["raw_xml_elements"],
                ir=report["xaml"]["xaml_ir_nodes"],
                errors=report["csharp"]["tree_sitter_error_nodes"],
                refs=report["resources"]["xaml_direct_references"],
                links=report["resources"]["parser_linked_references"],
                unresolved=report["unresolved_count"],
                impact=report["migration_impact"],
            )
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 工程执行成功率只说明七个阶段未抛出异常。",
            "- 文件级覆盖只验证输入与产物的一一对应和 ID/路径唯一性。",
            "- 结构覆盖比较原始语法结构与当前 IR，不自动证明字段语义正确。",
            "- 语义引用覆盖与资源闭包由静态规则审计；候选、动态与框架约定仍需显式 unresolved/unsupported 或人工核验。",
            "- 解析率是覆盖/显式处理率，不是人工 GT 下的语义正确率；显式 unsupported/unresolved 计入已处理单位。",
            "- 本数据集用于发现并修复通用问题，不构成对未知仓库的泛化能力证明。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repos-root", type=Path, default=Path("repos"))
    parser.add_argument("--parse-root", type=Path, default=DEFAULT_PARSE_ROOT)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--project", action="append", default=[])
    parser.add_argument(
        "--enforce-rate-threshold",
        action="store_true",
        help="若总体或任一解析器低于 90% 则以非零状态退出；报告仍会完整写出",
    )
    args = parser.parse_args()

    manifest = read_json(args.manifest)
    selected = [
        candidate
        for candidate in manifest.get("candidates", [])
        if candidate.get("status") in SELECTED_STATUSES
    ]
    if args.project:
        requested = set(args.project)
        selected = [item for item in selected if item.get("local_dir") in requested]
        missing = requested - {str(item["local_dir"]) for item in selected}
        if missing:
            parser.error(f"项目不在保留清单中: {', '.join(sorted(missing))}")

    reports: list[dict[str, Any]] = []
    for index, candidate in enumerate(selected, start=1):
        project_name = str(candidate["local_dir"])
        print(f"[{index}/{len(selected)}] 审计 {project_name}")
        report = audit_project(
            candidate, repos_root=args.repos_root, parse_root=args.parse_root
        )
        reports.append(report)
        write_json(args.report_root / "projects" / f"{project_name}.json", report)

    aggregate = _aggregate(reports)
    index = {
        "schema_version": 2,
        "id_scheme": SOURCE_ID_SCHEME,
        "manifest": args.manifest.as_posix(),
        "parse_root": args.parse_root.as_posix(),
        "selected_statuses": sorted(SELECTED_STATUSES),
        "expected_project_count": len(
            [
                item
                for item in manifest.get("candidates", [])
                if item.get("status") in SELECTED_STATUSES
            ]
        ),
        "audited_project_count": len(reports),
        "projects": [report["project"] for report in reports],
        "aggregate": aggregate,
        "parser_rate_report": "parser-rates.json",
        "project_reports": {
            report["project"]: f"projects/{report['project']}.json"
            for report in reports
        },
    }
    write_json(args.report_root / "audit-index.json", index)
    parser_rate_document = {
        "schema_version": 1,
        "threshold": PARSER_RATE_THRESHOLD,
        "aggregate": aggregate["parser_rates"],
        "projects": {
            report["project"]: report["parser_rates"] for report in reports
        },
    }
    write_json(args.report_root / "parser-rates.json", parser_rate_document)
    parser_rate_markdown = args.report_root / "parser-rates.md"
    parser_rate_markdown.write_text(
        _render_parser_rate_report(reports, aggregate), encoding="utf-8"
    )
    write_json(
        args.report_root / "unsupported-unresolved.json",
        {
            "schema_version": 1,
            "unsupported": {
                report["project"]: report["unsupported"] for report in reports
            },
            "unresolved": {
                report["project"]: report["unresolved"] for report in reports
            },
        },
    )
    report_path = args.report_root / "completeness-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(reports, aggregate), encoding="utf-8")
    print(f"审计索引: {args.report_root / 'audit-index.json'}")
    print(f"逐项目报告: {args.report_root / 'projects'}")
    print(f"汇总报告: {report_path}")
    print(f"解析率报告: {parser_rate_markdown}")
    overall = aggregate["parser_rates"]["overall"]
    print(
        f"解析率门槛: {overall['percentage']:.2f}% / "
        f"{PARSER_RATE_THRESHOLD * 100:.0f}%，"
        f"{'通过' if overall['passed'] else '不通过'}"
    )
    if args.enforce_rate_threshold and not overall["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
