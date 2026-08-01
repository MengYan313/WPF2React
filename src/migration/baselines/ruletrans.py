"""RuleTrans-MUI：不使用 LLM/RAG 的确定性 XAML→MUI 适配基线。"""

from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.common.logging import get_logger
from src.common.progress import progress
from src.common.source_identity import (
    component_name_from_page_id,
    normalize_page_id,
    repository_relative_id,
    target_relative_path,
)

from .common import (
    METHOD_RULETRANS,
    BaselineRunPaths,
    copy_binary_assets,
    create_target_skeleton,
    utc_now,
    write_json,
    write_jsonl,
)


_PRESENTATION_NAMESPACE = "http://schemas.microsoft.com/winfx/2006/xaml/presentation"
_PAGE_ROOTS = {"Window", "Page", "UserControl", "NavigationWindow"}
_PROPERTY_ONLY_TAGS = {
    "Application.Resources",
    "ColumnDefinition",
    "DataGrid.Columns",
    "Grid.ColumnDefinitions",
    "Grid.RowDefinitions",
    "ResourceDictionary",
    "RowDefinition",
    "Setter",
    "Style",
    "Window.Resources",
}

_SIMPLE_COMPONENT_RULES = {
    "Border": "Box",
    "Canvas": "Box",
    "ContentControl": "Box",
    "DockPanel": "Box",
    "Ellipse": "Box",
    "Frame": "Box",
    "Grid": "Box",
    "GroupBox": "Box",
    "ItemsControl": "List",
    "Label": "Typography",
    "ListBox": "List",
    "ListBoxItem": "ListItem",
    "ListView": "List",
    "MenuItem": "MenuItem",
    "ProgressBar": "LinearProgress",
    "Rectangle": "Box",
    "ScrollViewer": "Box",
    "Separator": "Divider",
    "Slider": "Slider",
    "TabItem": "Tab",
    "TextBlock": "Typography",
    "ToolBar": "Stack",
    "Viewbox": "Box",
    "WrapPanel": "Stack",
}


@dataclass(frozen=True)
class RuleAction:
    """从显式 XAML 事件与同名 code-behind 中确定性抽取的动作。"""

    kind: str
    target: str = ""


def _split_expanded_name(value: Any) -> tuple[str, str]:
    if not isinstance(value, str):
        return "", ""
    if value.startswith("{") and "}" in value:
        namespace, local = value[1:].split("}", 1)
        return namespace, local
    return "", value.split(":")[-1]


def _local_name(value: Any) -> str:
    return _split_expanded_name(value)[1]


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.replace("_", "").split()).strip()


def _js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _jsx_data_attr(name: str, value: str) -> str:
    return f"{name}={{{_js_string(value)}}}"


def _parse_number(value: str | None) -> int | float | None:
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


class RuleTransEngine:
    """将单个 XAML 页面递归转换为一个 TSX 文件。"""

    def __init__(
        self,
        source_file: Path,
        root: Any,
        component_name: str,
        *,
        event_actions: Mapping[str, RuleAction] | None = None,
    ) -> None:
        self.source_file = source_file
        self.root = root
        self.component_name = component_name
        self.event_actions = dict(event_actions or {})
        self.imports: set[str] = set()
        self.navigation_targets: set[str] = set()
        self.unsupported: list[dict[str, str]] = []
        self.node_count = 0

    def render(self) -> str:
        is_dialog = self.component_name != "MainWindow" and (
            self.component_name.endswith("Dialog")
            or self.component_name.endswith("DialogBox")
            or _local_name(self.root.tag) == "Window"
        )
        body_parts = [
            self._translate_element(child, f"root.{index}")
            for index, child in enumerate(self._visual_children(self.root))
        ]
        body = "\n".join(part for part in body_parts if part).strip()
        if not body:
            self.imports.add("Box")
            body = '<Box data-empty-wpf-page="true" />'

        if self.navigation_targets:
            dialog_nodes = "\n".join(
                f"<{target} open={{{self._state_name(target)}}} "
                f"onClose={{() => {self._setter_name(target)}(false)}} />"
                for target in sorted(self.navigation_targets)
            )
            body = f"{body}\n{dialog_nodes}"

        root_attrs = self._common_attributes(self.root)
        root_attrs.append(_jsx_data_attr("data-wpf-page", self.component_name))
        state_declarations = ""
        if self.navigation_targets:
            state_declarations = "\n".join(
                f"  const [{self._state_name(target)}, {self._setter_name(target)}] = "
                "useState(false);"
                for target in sorted(self.navigation_targets)
            ) + "\n"

        if is_dialog:
            self.imports.update({"Dialog", "DialogContent"})
            props_name = f"{self.component_name}Props"
            component = (
                f"export interface {props_name} {{\n"
                "  open: boolean;\n"
                "  onClose: () => void;\n"
                "}\n\n"
                f"export function {self.component_name}({{ open, onClose }}: {props_name}) {{\n"
                f"{state_declarations}"
                f"  return (\n    <Dialog open={{open}} onClose={{onClose}} {' '.join(root_attrs)}>\n"
                f"      <DialogContent>\n{self._indent(body, 8)}\n      </DialogContent>\n"
                "    </Dialog>\n  );\n}\n\n"
                f"export default {self.component_name};\n"
            )
        else:
            self.imports.add("Box")
            component = (
                f"export function {self.component_name}() {{\n"
                f"{state_declarations}"
                f"  return (\n    <Box {' '.join(root_attrs)}>\n"
                f"{self._indent(body, 6)}\n    </Box>\n  );\n}}\n\n"
                f"export default {self.component_name};\n"
            )

        imports = ", ".join(sorted(self.imports))
        support_imports = []
        if self.navigation_targets:
            support_imports.append("import { useState } from 'react';")
            support_imports.extend(
                f"import {{ {target} }} from './{target}';"
                for target in sorted(self.navigation_targets)
            )
        support_prefix = "\n".join(support_imports)
        if support_prefix:
            support_prefix += "\n"
        return (
            f"{support_prefix}"
            f"import {{ {imports} }} from '@mui/material';\n\n"
            "// Generated deterministically by RuleTrans-MUI.\n"
            f"{component}"
        )

    @staticmethod
    def _state_name(target: str) -> str:
        return target[0].lower() + target[1:] + "Open"

    @staticmethod
    def _setter_name(target: str) -> str:
        return "set" + target + "Open"

    @staticmethod
    def _indent(value: str, spaces: int) -> str:
        prefix = " " * spaces
        return "\n".join(prefix + line if line else line for line in value.splitlines())

    @staticmethod
    def _attributes(element: Any) -> dict[str, str]:
        attributes: dict[str, str] = {}
        for raw_name, raw_value in element.attrib.items():
            attributes[_local_name(raw_name)] = str(raw_value)
        return attributes

    @staticmethod
    def _visual_children(element: Any) -> Iterable[Any]:
        for child in element:
            if not isinstance(getattr(child, "tag", None), str):
                continue
            local = _local_name(child.tag)
            if "." in local or local in _PROPERTY_ONLY_TAGS or local.endswith("Resources"):
                continue
            yield child

    def _translate_element(self, element: Any, node_path: str) -> str:
        self.node_count += 1
        namespace, tag = _split_expanded_name(element.tag)
        attrs = self._attributes(element)
        children = list(self._visual_children(element))
        child_code = [
            self._translate_element(child, f"{node_path}.{index}")
            for index, child in enumerate(children)
        ]
        translated_children = "\n".join(code for code in child_code if code)
        text = self._visible_text(element, attrs)

        if namespace and namespace != _PRESENTATION_NAMESPACE:
            return self._unsupported_placeholder(tag, node_path, translated_children, text)

        if tag == "Button":
            return self._simple_tag("Button", element, attrs, translated_children, text)
        if tag == "TextBox":
            self.imports.add("TextField")
            props = self._common_attributes(element)
            props.append('variant="outlined"')
            binding = self._binding_path(attrs.get("Text", ""))
            if binding:
                props.append(_jsx_data_attr("data-binding", binding))
                props.append('defaultValue=""')
            elif attrs.get("Text"):
                props.append(_jsx_data_attr("defaultValue", attrs["Text"]))
            if attrs.get("AcceptsReturn", "").casefold() == "true":
                props.append("multiline")
            return f"<TextField {' '.join(props)} />"
        if tag == "ComboBox":
            self.imports.update({"MenuItem", "Select"})
            props = self._common_attributes(element)
            props.append('defaultValue=""')
            binding = self._binding_path(
                attrs.get("SelectedValue", "") or attrs.get("ItemsSource", "")
            )
            if binding:
                props.append(_jsx_data_attr("data-binding", binding))
            options = translated_children or '<MenuItem value="">未提供静态选项</MenuItem>'
            return f"<Select {' '.join(props)}>\n{self._indent(options, 2)}\n</Select>"
        if tag == "CheckBox":
            self.imports.update({"Checkbox", "FormControlLabel"})
            label = attrs.get("Content") or text or attrs.get("AutomationProperties.Name", "")
            props = self._common_attributes(element, exclude_label=True)
            return (
                f"<FormControlLabel {' '.join(props)} control={{<Checkbox />}} "
                f"label={{{_js_string(_clean_text(label))}}} />"
            )
        if tag == "RadioButton":
            self.imports.update({"FormControlLabel", "Radio"})
            label = attrs.get("Content") or text or attrs.get("AutomationProperties.Name", "")
            props = self._common_attributes(element, exclude_label=True)
            return (
                f"<FormControlLabel {' '.join(props)} control={{<Radio />}} "
                f"label={{{_js_string(_clean_text(label))}}} />"
            )
        if tag == "StackPanel":
            self.imports.add("Stack")
            props = self._common_attributes(element)
            direction = "row" if attrs.get("Orientation", "").casefold() == "horizontal" else "column"
            props.append(f'direction="{direction}"')
            return self._wrap("Stack", props, translated_children, text)
        if tag == "Menu":
            self.imports.add("Menu")
            props = self._common_attributes(element)
            props.extend(("open={false}", "onClose={() => undefined}"))
            return self._wrap("Menu", props, translated_children, text)
        if tag == "DataGrid":
            return self._translate_data_grid(element, attrs)
        if tag == "Image":
            self.imports.add("Box")
            props = self._common_attributes(element)
            props.append('component="img"')
            source = attrs.get("Source", "")
            if source and not source.startswith("{"):
                props.append(_jsx_data_attr("src", f"/{source.lstrip('/')}"))
                props.append(_jsx_data_attr("alt", attrs.get("AutomationProperties.Name", "")))
            else:
                props.append(_jsx_data_attr("data-unresolved-source", source or "missing"))
            return f"<Box {' '.join(props)} />"
        if tag == "PasswordBox":
            self.imports.add("TextField")
            props = self._common_attributes(element)
            props.extend(('type="password"', 'defaultValue=""'))
            return f"<TextField {' '.join(props)} />"
        if tag == "TabControl":
            self.imports.add("Tabs")
            props = self._common_attributes(element)
            props.extend(("value={0}", "onChange={() => undefined}"))
            return self._wrap("Tabs", props, translated_children, text)

        component = _SIMPLE_COMPONENT_RULES.get(tag)
        if component:
            return self._simple_tag(component, element, attrs, translated_children, text)
        return self._unsupported_placeholder(tag, node_path, translated_children, text)

    def _simple_tag(
        self,
        component: str,
        element: Any,
        attrs: dict[str, str],
        children: str,
        text: str,
    ) -> str:
        self.imports.add(component)
        if component == "Box" and _local_name(element.tag) == "Grid":
            props = self._common_attributes(element, extra_sx={"display": "grid"})
        else:
            props = self._common_attributes(element)
        if component == "Stack" and _local_name(element.tag) in {"ToolBar", "WrapPanel"}:
            props.append('direction="row"')
        elif component == "LinearProgress":
            props.append('variant="determinate"')
            props.append("value={0}")
        elif component == "Slider":
            props.append("defaultValue={0}")
        elif component == "Tab":
            label = attrs.get("Header") or attrs.get("Content") or text or "Tab"
            props.append(f"label={{{_js_string(_clean_text(label))}}}")
            return f"<Tab {' '.join(props)} />"
        return self._wrap(component, props, children, text)

    @staticmethod
    def _wrap(component: str, props: list[str], children: str, text: str) -> str:
        content_parts = []
        if text:
            content_parts.append(html.escape(text))
        if children:
            content_parts.append(children)
        if not content_parts:
            return f"<{component} {' '.join(props)} />"
        content = "\n".join(content_parts)
        return f"<{component} {' '.join(props)}>\n{RuleTransEngine._indent(content, 2)}\n</{component}>"

    def _unsupported_placeholder(
        self,
        tag: str,
        node_path: str,
        children: str,
        text: str,
    ) -> str:
        self.imports.add("Box")
        self.unsupported.append({"node_path": node_path, "wpf_tag": tag})
        props = [
            _jsx_data_attr("data-unsupported-wpf", tag),
            'role="group"',
        ]
        return self._wrap("Box", props, children, text or f"Unsupported: {tag}")

    def _common_attributes(
        self,
        element: Any,
        *,
        exclude_label: bool = False,
        extra_sx: Mapping[str, Any] | None = None,
    ) -> list[str]:
        attrs = self._attributes(element)
        props: list[str] = []
        name = attrs.get("Name") or attrs.get("x:Name")
        if name:
            props.append(_jsx_data_attr("id", re.sub(r"[^A-Za-z0-9_-]", "-", name)))
            props.append(_jsx_data_attr("data-wpf-name", name))
        label = attrs.get("AutomationProperties.Name")
        if label and not exclude_label:
            props.append(_jsx_data_attr("aria-label", _clean_text(label)))
        if attrs.get("IsEnabled", "").casefold() == "false":
            props.append("disabled")
        event_name = attrs.get("Click") or attrs.get("Command")
        if event_name:
            action = self.event_actions.get(event_name)
            if action and action.kind == "open" and action.target != self.component_name:
                self.navigation_targets.add(action.target)
                props.append(
                    f"onClick={{() => {self._setter_name(action.target)}(true)}}"
                )
                props.append(_jsx_data_attr("data-navigation-target", action.target))
            elif action and action.kind == "close":
                props.append(
                    "onClick={onClose}"
                    if self.component_name != "MainWindow"
                    else "onClick={() => window.close()}"
                )
            else:
                props.append("onClick={() => undefined}")
            props.append(_jsx_data_attr("data-source-event", event_name))
        style = attrs.get("Style")
        if style:
            props.append(_jsx_data_attr("data-wpf-style", style))
        binding_values = [
            value for value in attrs.values() if isinstance(value, str) and "{Binding" in value
        ]
        binding_values.extend(self._property_element_bindings(element))
        if binding_values:
            props.append(
                _jsx_data_attr(
                    "data-wpf-binding",
                    "; ".join(filter(None, (self._binding_path(v) for v in binding_values))),
                )
            )

        sx: dict[str, Any] = dict(extra_sx or {})
        if attrs.get("Visibility", "").casefold() in {"collapsed", "hidden"}:
            sx["display"] = "none"
        for source, target in (("Width", "width"), ("Height", "height"), ("MinWidth", "minWidth"), ("MinHeight", "minHeight")):
            number = _parse_number(attrs.get(source))
            if number is not None:
                sx[target] = number
        margin = attrs.get("Margin")
        if margin:
            values = [part for part in re.split(r"[ ,]+", margin.strip()) if part]
            if all(_parse_number(part) is not None for part in values):
                px = [f"{_parse_number(part)}px" for part in values]
                sx["margin"] = " ".join(px)
        row = _parse_number(attrs.get("Grid.Row"))
        column = _parse_number(attrs.get("Grid.Column"))
        row_span = _parse_number(attrs.get("Grid.RowSpan"))
        column_span = _parse_number(attrs.get("Grid.ColumnSpan"))
        if isinstance(row, int):
            sx["gridRowStart"] = row + 1
        if isinstance(column, int):
            sx["gridColumnStart"] = column + 1
        if isinstance(row_span, int):
            sx["gridRowEnd"] = f"span {row_span}"
        if isinstance(column_span, int):
            sx["gridColumnEnd"] = f"span {column_span}"
        if sx:
            props.append(f"sx={{{json.dumps(sx, ensure_ascii=False)}}}")
        return props

    def _property_element_bindings(self, element: Any) -> list[str]:
        bindings: list[str] = []
        for descendant in element.iter():
            if descendant is element or _local_name(getattr(descendant, "tag", "")) != "Binding":
                continue
            attrs = self._attributes(descendant)
            path = attrs.get("Path") or attrs.get("XPath")
            if path:
                bindings.append(f"{{Binding Path={path}}}")
        return bindings

    @staticmethod
    def _binding_path(value: str) -> str:
        if "{Binding" not in value:
            return ""
        path_match = re.search(r"(?:Path\s*=\s*)?([A-Za-z_][A-Za-z0-9_.]*)", value[8:])
        return path_match.group(1) if path_match else ""

    def _visible_text(self, element: Any, attrs: dict[str, str]) -> str:
        candidate = attrs.get("Content") or attrs.get("Header") or ""
        if candidate and not candidate.startswith("{"):
            return _clean_text(candidate)
        # XAML 属性元素（如 Button.ToolTip）会使真正的按钮文本落到 child.tail。
        # 这里只收集当前节点的直接文本与直接子节点 tail，避免把 Tooltip 内容当标签。
        direct_parts = [getattr(element, "text", None)]
        direct_parts.extend(getattr(child, "tail", None) for child in element)
        direct = _clean_text(" ".join(part for part in direct_parts if part))
        return "" if direct.startswith("{") else direct

    def _translate_data_grid(self, element: Any, attrs: dict[str, str]) -> str:
        self.imports.update(
            {"Paper", "Table", "TableBody", "TableCell", "TableContainer", "TableHead", "TableRow"}
        )
        headers: list[str] = []
        for descendant in element.iter():
            tag = _local_name(getattr(descendant, "tag", ""))
            if tag in {"DataGridTextColumn", "DataGridCheckBoxColumn", "DataGridTemplateColumn"}:
                header = self._attributes(descendant).get("Header")
                if header:
                    headers.append(_clean_text(header))
        if not headers:
            headers.append("Data")
        header_cells = "\n".join(
            f"<TableCell>{html.escape(header)}</TableCell>" for header in headers
        )
        binding = self._binding_path(attrs.get("ItemsSource", ""))
        binding_attr = f" {_jsx_data_attr('data-binding', binding)}" if binding else ""
        return (
            f"<TableContainer component={{Paper}}{binding_attr}>\n"
            "  <Table>\n    <TableHead>\n      <TableRow>\n"
            f"{self._indent(header_cells, 8)}\n"
            "      </TableRow>\n    </TableHead>\n"
            "    <TableBody />\n  </Table>\n</TableContainer>"
        )


class RuleTransMUIRunner:
    """运行整个 RuleTrans-MUI 项目基线。"""

    def __init__(self, paths: BaselineRunPaths) -> None:
        if paths.method_id != METHOD_RULETRANS:
            raise ValueError("RuleTransMUIRunner 只接受 RuleTrans-MUI 路径")
        self.paths = paths
        self.logger = get_logger(__name__)

    def run(self, page_names: Sequence[str] | None = None) -> dict[str, Any]:
        started_at = utc_now()
        started = time.perf_counter()
        self.paths.prepare()
        skeleton_files = create_target_skeleton(self.paths.result_root)
        assets = copy_binary_assets(self.paths.source_root, self.paths.result_root)
        records: list[dict[str, Any]] = []
        known_pages = self._discover_page_names()
        requested_pages = list(
            dict.fromkeys(normalize_page_id(page_id) for page_id in (page_names or []))
        )
        selected = set(requested_pages)

        xaml_paths = (
            [self.paths.source_root / page_id for page_id in requested_pages]
            if requested_pages
            else sorted(self.paths.source_root.rglob("*.xaml"))
        )
        for xaml_path in progress(
            xaml_paths,
            desc="RuleTrans 页面",
            unit="文件",
            leave=False,
        ):
            page_id = repository_relative_id(xaml_path, self.paths.source_root)
            if selected and page_id not in selected:
                continue
            page_record = self._convert_if_page(xaml_path, known_pages)
            if page_record is not None:
                records.append(page_record)

        missing = selected - {record["page_id"] for record in records}
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"指定页面不存在或不是可迁移页面: {missing_text}")

        successful_pages = [
            record for record in records if record["status"] == "success"
        ]
        entry_page = self._write_app_entry(successful_pages)

        status = (
            "success"
            if records and all(record["status"] == "success" for record in records)
            else "failed"
        )
        summary = {
            "method_id": METHOD_RULETRANS,
            "run_id": self.paths.run_id,
            "project_id": self.paths.project_id,
            "status": status,
            "started_at": started_at,
            "finished_at": utc_now(),
            "wall_time_seconds": round(time.perf_counter() - started, 6),
            "source_root": str(self.paths.source_root),
            "result_root": str(self.paths.result_root),
            "artifact_root": str(self.paths.artifact_root),
            "page_count": len(records),
            "page_filter": requested_pages or None,
            "successful_pages": sum(r["status"] == "success" for r in records),
            "unsupported_control_count": sum(len(r.get("unsupported", [])) for r in records),
            "entry_page": entry_page,
            "llm_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "skeleton_files": skeleton_files,
            "binary_assets": assets,
        }
        write_json(self.paths.artifact_root / "run_manifest.json", summary)
        write_jsonl(self.paths.artifact_root / "generation_records.jsonl", records)
        self.logger.info(
            "RuleTrans-MUI 完成: %s/%s 页面，unsupported=%s",
            summary["successful_pages"],
            summary["page_count"],
            summary["unsupported_control_count"],
        )
        return summary

    def _convert_if_page(
        self,
        xaml_path: Path,
        known_pages: Mapping[str, str],
    ) -> dict[str, Any] | None:
        relative = xaml_path.relative_to(self.paths.source_root)
        page_id = repository_relative_id(xaml_path, self.paths.source_root)
        try:
            root = self._parse_xaml(xaml_path)
            root_tag = _local_name(root.tag)
            if root_tag not in _PAGE_ROOTS:
                return None
            component_name = self._component_name(root, xaml_path)
            engine = RuleTransEngine(
                xaml_path,
                root,
                component_name,
                event_actions=self._discover_event_actions(
                    xaml_path,
                    root,
                    known_pages,
                ),
            )
            code = engine.render()
            output = self.paths.result_root / target_relative_path(page_id, ".tsx")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(code, encoding="utf-8")
            return {
                "method_id": METHOD_RULETRANS,
                "run_id": self.paths.run_id,
                "project_id": self.paths.project_id,
                "page_id": page_id,
                "component_name": component_name,
                "source_file": str(relative),
                "target_file": output.relative_to(self.paths.result_root).as_posix(),
                "status": "success",
                "translated_nodes": engine.node_count,
                "unsupported": engine.unsupported,
                "navigation_targets": sorted(engine.navigation_targets),
            }
        except Exception as exc:
            self.logger.error("RuleTrans-MUI 页面转换失败: %s: %s", relative, exc)
            return {
                "method_id": METHOD_RULETRANS,
                "run_id": self.paths.run_id,
                "project_id": self.paths.project_id,
                "page_id": page_id,
                "source_file": str(relative),
                "status": "failed",
                "error": str(exc),
            }

    def _discover_page_names(self) -> dict[str, str]:
        candidates: dict[str, set[str]] = {}
        for xaml_path in sorted(self.paths.source_root.rglob("*.xaml")):
            try:
                root = self._parse_xaml(xaml_path)
            except Exception:
                continue
            if _local_name(root.tag) in _PAGE_ROOTS:
                component_name = self._component_name(root, xaml_path)
                full_name = self._source_class_full_name(root, xaml_path)
                for symbol in {full_name, full_name.rsplit(".", 1)[-1]}:
                    candidates.setdefault(symbol, set()).add(component_name)
        # 同一源码类符号指向多个页面时保持未解析，绝不按遍历顺序覆盖。
        return {
            symbol: next(iter(components))
            for symbol, components in candidates.items()
            if len(components) == 1
        }

    def _discover_event_actions(
        self,
        xaml_path: Path,
        root: Any,
        known_pages: Mapping[str, str],
    ) -> dict[str, RuleAction]:
        code_path = xaml_path.with_suffix(".cs")
        if not code_path.is_file():
            return {}
        code = code_path.read_text(encoding="utf-8-sig")
        method_bodies = self._extract_method_bodies(code)
        actions: dict[str, RuleAction] = {}
        event_names: set[str] = set()
        for element in root.iter():
            if not isinstance(getattr(element, "tag", None), str):
                continue
            attrs = RuleTransEngine._attributes(element)
            event_name = attrs.get("Click") or attrs.get("Command")
            if event_name:
                event_names.add(event_name)

        for event_name in sorted(event_names):
            handler_name = self._resolve_handler_name(event_name, code, method_bodies)
            body = method_bodies.get(handler_name, "")
            current_component = self._component_name(root, xaml_path)
            target = next(
                (
                    target_component
                    for source_class, target_component in sorted(known_pages.items())
                    if target_component != current_component
                    and re.search(rf"\bnew\s+{re.escape(source_class)}\b", body)
                    and re.search(r"\.Show(?:Dialog)?\s*\(", body)
                ),
                "",
            )
            if target:
                actions[event_name] = RuleAction(kind="open", target=target)
            elif re.search(r"\bClose\s*\(", body) or re.search(
                r"\bDialogResult\s*=", body
            ):
                actions[event_name] = RuleAction(kind="close")
        return actions

    @staticmethod
    def _resolve_handler_name(
        event_name: str,
        code: str,
        method_bodies: Mapping[str, str],
    ) -> str:
        if event_name in method_bodies:
            return event_name
        command_name = event_name.rsplit(".", 1)[-1]
        binding_match = re.search(
            rf"(?P<variable>[A-Za-z_]\w*)\s*=\s*new\s+CommandBinding\s*\(\s*"
            rf"{re.escape(command_name)}\s*\)\s*;",
            code,
        )
        if binding_match:
            handler_match = re.search(
                rf"\b{re.escape(binding_match.group('variable'))}\.Executed\s*\+=\s*"
                r"(?P<handler>[A-Za-z_]\w*)\s*;",
                code,
            )
            if handler_match:
                return handler_match.group("handler")
        stem = command_name.removesuffix("Command").casefold()
        return next(
            (
                name
                for name in sorted(method_bodies)
                if stem and stem in name.casefold() and name.endswith("_Executed")
            ),
            "",
        )

    @staticmethod
    def _extract_method_bodies(code: str) -> dict[str, str]:
        declaration = re.compile(
            r"\b(?:public|private|protected|internal)\s+"
            r"(?:static\s+)?(?:async\s+)?[A-Za-z_][\w<>,.?\[\]]*\s+"
            r"(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
        )
        bodies: dict[str, str] = {}
        for match in declaration.finditer(code):
            depth = 1
            index = match.end()
            while index < len(code) and depth:
                if code[index] == "{":
                    depth += 1
                elif code[index] == "}":
                    depth -= 1
                index += 1
            if depth == 0:
                bodies[match.group("name")] = code[match.end() : index - 1]
        return bodies

    def _write_app_entry(self, successful_pages: list[dict[str, Any]]) -> str | None:
        if not successful_pages:
            return None
        entry_record = next(
            (
                record
                for record in successful_pages
                if Path(str(record.get("page_id", ""))).stem == "MainWindow"
            ),
            successful_pages[0],
        )
        entry_page = str(entry_record["component_name"])
        entry_page_id = str(entry_record["page_id"])
        entry_target = target_relative_path(entry_page_id, ".tsx")
        import_path = "./" + entry_target.with_suffix("").as_posix()
        target = self.paths.result_root / "App.tsx"
        entry_code = (self.paths.result_root / entry_target).read_text(
            encoding="utf-8"
        )
        entry_requires_dialog_props = f"interface {entry_page}Props" in entry_code
        if not entry_requires_dialog_props:
            target.write_text(
                f"import {{ {entry_page} }} from '{import_path}';\n\n"
                "export function App() {\n"
                f"  return <{entry_page} />;\n"
                "}\n\n"
                "export default App;\n",
                encoding="utf-8",
            )
        else:
            target.write_text(
                "import { useState } from 'react';\n"
                f"import {{ {entry_page} }} from '{import_path}';\n\n"
                "export function App() {\n"
                "  const [open, setOpen] = useState(true);\n"
                f"  return <{entry_page} open={{open}} onClose={{() => setOpen(false)}} />;\n"
                "}\n\n"
                "export default App;\n",
                encoding="utf-8",
            )
        return entry_page_id

    @staticmethod
    def _parse_xaml(path: Path) -> Any:
        try:
            from lxml import etree

            parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
            return etree.parse(str(path), parser).getroot()
        except ImportError:
            from xml.etree import ElementTree

            return ElementTree.parse(path).getroot()

    def _component_name(self, root: Any, path: Path) -> str:
        del root
        return component_name_from_page_id(
            repository_relative_id(path, self.paths.source_root)
        )

    @staticmethod
    def _source_class_name(root: Any, path: Path) -> str:
        class_name = RuleTransMUIRunner._source_class_full_name(root, path).rsplit(
            ".", 1
        )[-1]
        candidate = class_name or path.stem
        sanitized = re.sub(r"[^A-Za-z0-9_]", "", candidate)
        if not sanitized:
            return "MigratedPage"
        if sanitized[0].isdigit():
            sanitized = f"Page{sanitized}"
        return sanitized

    @staticmethod
    def _source_class_full_name(root: Any, path: Path) -> str:
        for raw_name, value in root.attrib.items():
            if _local_name(raw_name) == "Class":
                return str(value)
        return path.stem
