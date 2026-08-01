"""面向 WPF 控件迁移的版本化 MUI 组件知识库。"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


def _tokens(text: str) -> list[str]:
    """拆分英文驼峰与中文短语，供小规模 BM25 检索使用。"""
    stopwords = {"component", "control", "custom", "mui", "widget", "wpf", "控件", "组件"}
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    parts = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", expanded.lower())
    tokens: list[str] = []
    for part in parts:
        if part in stopwords:
            continue
        tokens.append(part)
        if re.fullmatch(r"[\u4e00-\u9fff]+", part) and len(part) > 2:
            tokens.extend(part[index : index + 2] for index in range(len(part) - 1))
    return tokens


class ComponentKnowledgeBase:
    """合并原始文档与结构化元数据，并提供本地稀疏检索。"""

    def __init__(self, documents_path: Path, catalog_path: Path) -> None:
        source_documents: dict[str, dict[str, Any]] = json.loads(
            documents_path.read_text(encoding="utf-8")
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.schema_version = catalog["schema_version"]
        self.target_versions = catalog["target_versions"]
        self.excluded_components: dict[str, str] = catalog.get(
            "excluded_components", {}
        )
        self.documents = {
            name: document
            for name, document in source_documents.items()
            if name not in self.excluded_components
        }
        self.metadata: dict[str, dict[str, Any]] = catalog["components"]
        unknown = sorted(set(self.metadata) - set(source_documents))
        if unknown:
            raise ValueError(f"结构化目录引用了未知 MUI 条目: {', '.join(unknown)}")

        self._document_tokens = {
            name: _tokens(self.search_text(name)) for name in self.documents
        }
        self._document_frequency = Counter(
            token
            for tokens in self._document_tokens.values()
            for token in set(tokens)
        )
        self._average_length = sum(map(len, self._document_tokens.values())) / len(
            self._document_tokens
        )

    def metadata_for(self, name: str) -> dict[str, Any]:
        return self.metadata.get(name, {})

    def search_text(self, name: str) -> str:
        document = self.documents[name]
        metadata = self.metadata_for(name)
        fields = [
            name,
            metadata.get("summary_zh", ""),
            document.get("description", ""),
            " ".join(metadata.get("aliases", [])),
            " ".join(metadata.get("keywords", [])),
            metadata.get("category", ""),
        ]
        return " ".join(field for field in fields if field)

    def aliases_for(self, name: str) -> list[str]:
        return [name, *self.metadata_for(name).get("aliases", [])]

    def lexical_scores(self, query: str) -> dict[str, float]:
        """返回按查询内最大值归一化的 BM25 分数。"""
        query_terms = Counter(_tokens(query))
        document_count = len(self._document_tokens)
        scores: dict[str, float] = {}
        for name, tokens in self._document_tokens.items():
            term_frequency = Counter(tokens)
            length_factor = 1 - 0.75 + 0.75 * len(tokens) / self._average_length
            score = 0.0
            for token, query_frequency in query_terms.items():
                frequency = term_frequency[token]
                if not frequency:
                    continue
                document_frequency = self._document_frequency[token]
                inverse_frequency = math.log(
                    1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                score += (
                    inverse_frequency
                    * frequency
                    * 2.2
                    / (frequency + 1.2 * length_factor)
                    * min(query_frequency, 2)
                )
            scores[name] = score
        maximum = max(scores.values(), default=0.0)
        return {
            name: score / maximum if maximum else 0.0
            for name, score in scores.items()
        }

    def render_document(self, name: str) -> str:
        """生成可直接注入迁移提示词的版本化组件契约。"""
        document = self.documents[name]
        metadata = self.metadata_for(name)
        target = self.target_versions
        lines = [
            f"目标版本：React {target['react']}，MUI {target['mui']}，TypeScript {target['typescript']}",
            f"组件类别：{metadata.get('category', '通用')}",
            f"用途：{metadata.get('summary_zh') or document.get('description', '')}",
        ]
        imports = metadata.get("imports", [])
        if imports:
            lines.append(f"允许导入：{', '.join(imports)}")
        constraints = metadata.get("constraints", [])
        if constraints:
            lines.append("迁移约束：" + "；".join(constraints))
        lines.extend(
            [
                "参考说明：" + document.get("description", ""),
                "参考代码：\n```tsx\n" + document.get("usage_example", "") + "\n```",
            ]
        )
        return "\n\n".join(lines)
