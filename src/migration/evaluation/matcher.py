"""可替换的组件判别器及默认确定性实现。"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Protocol, Sequence

from .models import ComponentMatch, ComponentSpec, MatchStatus


_JSX_TAG_PATTERN = re.compile(r"<([A-Z][A-Za-z0-9_.]*)\b")


class ComponentJudge(Protocol):
    """组件定位接口；LLM 判别器可以实现同一契约。"""

    def judge(
        self,
        components: Sequence[ComponentSpec],
        target_root: Path,
    ) -> list[ComponentMatch]:
        """为每个源组件返回一个定位结果，顺序必须与输入一致。"""


class _Occurrence:
    def __init__(self, file_path: Path, tag: str, start: int, content: str) -> None:
        self.file_path = file_path
        self.tag = tag
        self.start = start
        self.line = content.count("\n", 0, start) + 1
        left = max(0, start - 300)
        right = min(len(content), start + 500)
        self.snippet = content[left:right]

    @property
    def key(self) -> tuple[Path, int]:
        return self.file_path, self.start


class DeterministicComponentJudge:
    """按页面、目标标签、名称和文本证据定位 TS/TSX 实现。

    同一 JSX occurrence 只分配给一个源组件，避免多个源节点重复命中同一个
    目标标签。该判别器只负责定位；最终成功仍由编译器决定。
    """

    def judge(
        self,
        components: Sequence[ComponentSpec],
        target_root: Path,
    ) -> list[ComponentMatch]:
        try:
            inventory = self._load_inventory(target_root)
        except OSError as exc:
            return [
                ComponentMatch(
                    component_id=component.component_id,
                    status=MatchStatus.EVALUATOR_ERROR,
                    evidence=[f"读取目标代码失败: {exc}"],
                )
                for component in components
            ]

        claimed: set[tuple[Path, int]] = set()
        results_by_id: dict[str, ComponentMatch] = {}
        components_by_page: dict[str, list[ComponentSpec]] = defaultdict(list)
        for component in components:
            components_by_page[component.page_id].append(component)

        for page_components in components_by_page.values():
            for component in page_components:
                results_by_id[component.component_id] = self._match_one(
                    component,
                    target_root,
                    inventory,
                    claimed,
                )

        return [results_by_id[component.component_id] for component in components]

    def _load_inventory(self, target_root: Path) -> dict[Path, str]:
        if not target_root.is_dir():
            return {}
        inventory: dict[Path, str] = {}
        for suffix in ("*.tsx", "*.ts"):
            for path in sorted(target_root.rglob(suffix)):
                if "node_modules" in path.parts or not path.is_file():
                    continue
                inventory[path.resolve()] = path.read_text(encoding="utf-8")
        return inventory

    def _match_one(
        self,
        component: ComponentSpec,
        target_root: Path,
        inventory: dict[Path, str],
        claimed: set[tuple[Path, int]],
    ) -> ComponentMatch:
        candidate_files, preferred_files = self._candidate_files(
            component, target_root, inventory
        )
        if not candidate_files:
            return ComponentMatch(
                component_id=component.component_id,
                status=MatchStatus.NOT_FOUND,
                evidence=["目标目录中没有符合页面或组件提示的 TS/TSX 文件"],
            )

        expected_tags = {
            hint.split(":")[-1].split(".")[-1]
            for hint in component.target_tag_hints + [component.source_tag]
            if hint
        }
        occurrences: list[tuple[int, _Occurrence, list[str]]] = []
        for file_path in candidate_files:
            content = inventory[file_path]
            for match in _JSX_TAG_PATTERN.finditer(content):
                occurrence = _Occurrence(file_path, match.group(1), match.start(), content)
                if occurrence.key in claimed or occurrence.tag not in expected_tags:
                    continue
                score, evidence = self._score_occurrence(
                    component,
                    occurrence,
                    preferred_files,
                )
                occurrences.append((score, occurrence, evidence))

        if occurrences:
            occurrences.sort(
                key=lambda item: (
                    -item[0],
                    str(item[1].file_path),
                    item[1].start,
                )
            )
            top_score = occurrences[0][0]
            tied_files = {
                item[1].file_path for item in occurrences if item[0] == top_score
            }
            if len(tied_files) > 1 and not preferred_files:
                return ComponentMatch(
                    component_id=component.component_id,
                    status=MatchStatus.AMBIGUOUS,
                    confidence=0.4,
                    evidence=["多个目标文件包含同分候选，无法唯一定位"],
                )

            _, selected, evidence = occurrences[0]
            claimed.add(selected.key)
            return ComponentMatch(
                component_id=component.component_id,
                status=MatchStatus.MATCHED,
                target_file=str(selected.file_path.relative_to(target_root)),
                target_symbol=selected.tag,
                target_line=selected.line,
                match_type="inline_jsx",
                confidence=0.95 if len(evidence) > 1 else 0.75,
                evidence=evidence,
            )

        symbol_match = self._match_symbol_or_text(
            component,
            target_root,
            candidate_files,
            preferred_files,
            inventory,
            claimed,
        )
        if symbol_match is not None:
            return symbol_match

        return ComponentMatch(
            component_id=component.component_id,
            status=MatchStatus.NOT_FOUND,
            evidence=["候选文件中未找到目标标签、符号、名称或文本证据"],
        )

    def _candidate_files(
        self,
        component: ComponentSpec,
        target_root: Path,
        inventory: dict[Path, str],
    ) -> tuple[list[Path], set[Path]]:
        preferred: set[Path] = set()
        for hint in component.target_file_hints:
            resolved = self._resolve_inside(target_root, hint)
            if resolved in inventory:
                preferred.add(resolved)

        name_hints = {
            value.casefold()
            for value in (
                component.source_name,
                *component.target_symbol_hints,
            )
            if value
        }
        name_candidates = {
            path
            for path in inventory
            if path.stem.casefold() in name_hints
        }

        if preferred:
            candidates = sorted(preferred | name_candidates)
        elif name_candidates:
            candidates = sorted(name_candidates)
        elif component.source_name or component.target_symbol_hints:
            candidates = sorted(inventory)
        else:
            candidates = []
        return candidates, preferred

    @staticmethod
    def _resolve_inside(target_root: Path, hint: str) -> Path:
        candidate = (target_root / hint).resolve()
        try:
            candidate.relative_to(target_root)
        except ValueError:
            return target_root / "__outside_target_root__"
        return candidate

    @staticmethod
    def _score_occurrence(
        component: ComponentSpec,
        occurrence: _Occurrence,
        preferred_files: set[Path],
    ) -> tuple[int, list[str]]:
        score = 10
        evidence = [f"目标 JSX 标签 <{occurrence.tag}> 与组件映射一致"]
        snippet_folded = occurrence.snippet.casefold()
        if occurrence.file_path in preferred_files:
            score += 5
            evidence.append("候选位于源页面对应的目标文件")
        if component.source_name and component.source_name.casefold() in snippet_folded:
            score += 8
            evidence.append(f"附近代码包含源名称 {component.source_name}")
        for text_hint in component.text_hints:
            if text_hint.casefold() in snippet_folded:
                score += 3
                evidence.append(f"附近代码包含文本证据 {text_hint}")
        return score, evidence

    def _match_symbol_or_text(
        self,
        component: ComponentSpec,
        target_root: Path,
        candidate_files: list[Path],
        preferred_files: set[Path],
        inventory: dict[Path, str],
        claimed: set[tuple[Path, int]],
    ) -> ComponentMatch | None:
        symbol_hints = [
            value
            for value in (
                component.source_name,
                *component.target_symbol_hints,
            )
            if value
        ]
        matches: list[tuple[int, Path, str, int, int, list[str]]] = []
        for file_path in candidate_files:
            content = inventory[file_path]
            for symbol in symbol_hints:
                pattern = re.compile(
                    rf"\b(?:function|class|const|let|var)\s+{re.escape(symbol)}\b"
                )
                found = pattern.search(content)
                if found and (file_path, found.start()) not in claimed:
                    score = 12 + (5 if file_path in preferred_files else 0)
                    line = content.count("\n", 0, found.start()) + 1
                    evidence = [f"找到目标符号 {symbol}"]
                    matches.append(
                        (score, file_path, symbol, line, found.start(), evidence)
                    )

            for text_hint in component.text_hints:
                position = content.casefold().find(text_hint.casefold())
                if position >= 0 and (file_path, position) not in claimed:
                    score = 5 + (5 if file_path in preferred_files else 0)
                    line = content.count("\n", 0, position) + 1
                    matches.append(
                        (
                            score,
                            file_path,
                            text_hint,
                            line,
                            position,
                            [f"找到目标文本证据 {text_hint}"],
                        )
                    )

        if not matches:
            return None
        matches.sort(key=lambda item: (-item[0], str(item[1]), item[3]))
        top_score = matches[0][0]
        top_files = {item[1] for item in matches if item[0] == top_score}
        if len(top_files) > 1 and not preferred_files:
            return ComponentMatch(
                component_id=component.component_id,
                status=MatchStatus.AMBIGUOUS,
                confidence=0.4,
                evidence=["名称或文本证据同时命中多个目标文件"],
            )

        _, file_path, symbol, line, selected_position, evidence = matches[0]
        claimed.add((file_path, selected_position))
        return ComponentMatch(
            component_id=component.component_id,
            status=MatchStatus.MATCHED,
            target_file=str(file_path.relative_to(target_root)),
            target_symbol=symbol,
            target_line=line,
            match_type="symbol_or_text",
            confidence=0.7,
            evidence=evidence,
        )
