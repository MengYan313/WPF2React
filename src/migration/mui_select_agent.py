"""按确定性映射和混合检索选择 MUI 组件。"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig, build_json_system_prompt
from src.llm.json_output import JsonOutputError

from .base import BaseMigrationAgent
from .component_knowledge import ComponentKnowledgeBase
from .json_schemas import DESCRIPTION_SCHEMA
from .messages import MUISelectionRequest, MUISelectionResponse

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


class MUISelectAgent(BaseMigrationAgent):
    """标准控件走规则映射，自建控件走名称、BM25 与向量融合检索。"""

    def __init__(
        self,
        mui_json_path: str = "rags/mui/mui_components.json",
        wpf_to_mui_mapping_path: str = "rags/mui/wpf_to_mui_mapping.json",
        component_catalog_path: str = "rags/mui/component_catalog.json",
        mapping_overrides_path: str = "rags/mui/wpf_mapping_overrides.json",
        llm_config: Optional[LLMConfig] = None,
        output_base_dir: str = "outputs",
        retrieval_enabled: bool = True,
        use_semantic_similarity: bool = True,
        semantic_model: str = "sentence-transformers",
        semantic_model_name: str = "all-MiniLM-L6-v2",
        minimum_confidence: float = 0.18,
    ) -> None:
        super().__init__(
            agent_type="MUISelectAgent",
            llm_config=llm_config or LLMConfig.json_mode_config(),
            output_base_dir=output_base_dir,
        )
        self.retrieval_enabled = retrieval_enabled
        self.mui_json_path = Path(mui_json_path)
        self.wpf_to_mui_mapping_path = Path(wpf_to_mui_mapping_path)
        self.component_catalog_path = Path(component_catalog_path)
        self.mapping_overrides_path = Path(mapping_overrides_path)
        self.minimum_confidence = minimum_confidence
        self.knowledge_base = (
            ComponentKnowledgeBase(self.mui_json_path, self.component_catalog_path)
            if retrieval_enabled
            else None
        )
        self.mui_components_index = (
            self.knowledge_base.documents if self.knowledge_base else {}
        )
        self.wpf_to_mui_mapping = self._load_mapping()

        self.use_semantic_similarity = use_semantic_similarity and retrieval_enabled
        self.semantic_model_type = semantic_model
        self.semantic_model_name = semantic_model_name
        self._embedding_model = None
        self._embedding_cache: OrderedDict[str, list[float]] = OrderedDict()
        self._embedding_cache_max_size = 2048
        if self.use_semantic_similarity:
            self._init_semantic_model()

    def _load_mapping(self) -> dict[str, Any]:
        mapping = json.loads(self.wpf_to_mui_mapping_path.read_text(encoding="utf-8"))
        if self.mapping_overrides_path.exists():
            mapping.update(
                json.loads(self.mapping_overrides_path.read_text(encoding="utf-8"))
            )
        return mapping

    def _init_semantic_model(self) -> None:
        if self.semantic_model_type != "sentence-transformers":
            raise ValueError("当前本地混合检索仅支持 sentence-transformers")
        if SentenceTransformer is None:
            raise ImportError("sentence-transformers 未安装，无法启用向量检索")
        self.logger.info("正在加载语义相似度模型: %s", self.semantic_model_name)
        self._embedding_model = SentenceTransformer(
            self.semantic_model_name, local_files_only=True
        )

    def _embedding(self, text: str) -> list[float]:
        if text in self._embedding_cache:
            self._embedding_cache.move_to_end(text)
            return self._embedding_cache[text]
        embedding = self._embedding_model.encode(text, convert_to_numpy=False).tolist()
        self._embedding_cache[text] = embedding
        if len(self._embedding_cache) > self._embedding_cache_max_size:
            self._embedding_cache.popitem(last=False)
        return embedding

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        left_length = sum(value * value for value in left) ** 0.5
        right_length = sum(value * value for value in right) ** 0.5
        return max(0.0, dot / (left_length * right_length))

    @staticmethod
    def _name_similarity(left: str, right: str) -> float:
        def normalize(value: str) -> str:
            return re.sub(r"[^a-z0-9]", "", value.lower())

        left_name = normalize(left)
        right_name = normalize(right)
        if left_name == right_name:
            return 1.0

        generic = {"component", "control", "custom", "extended", "ex", "view", "widget"}

        def words(value: str) -> list[str]:
            expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
            return [
                word.lower()
                for word in re.findall(r"[A-Za-z0-9]+", expanded)
                if word.lower() not in generic
            ]

        left_words = words(left)
        right_words = words(right)
        if not left_words or not right_words:
            return 0.0
        overlap = set(left_words) & set(right_words)
        if not overlap:
            return 0.0
        return len(overlap) / len(set(left_words) | set(right_words))

    async def _generate_wpf_description(self, message: MUISelectionRequest) -> str:
        system_prompt = build_json_system_prompt(
            role="你是 WPF UI 控件分析专家。",
            goal="生成用于 MUI 组件检索的标准化控件用途说明。",
            success_criteria=(
                "用一到两句中文概括主要用途、用户可见行为和关键交互。",
                "优先说明输入、选择、反馈、导航、数据展示或布局等可迁移语义。",
            ),
            constraints=(
                "只依据控件标签、属性、语义引用和源码。",
                "不直接推荐 MUI 组件，不推测未展示的业务逻辑。",
            ),
            field_rules=("description 只包含说明正文。",),
        )
        user_prompt = f"""请描述以下 WPF 控件。

## 标签
{message.wpf_tag}

## 属性
{json.dumps(message.attributes, ensure_ascii=False)}

## 语义引用
{json.dumps(message.semantic_references, ensure_ascii=False)}

## 源码
```xml
{message.wpf_source[:4000]}
```"""
        try:
            result = await self.call_json(
                system_prompt, user_prompt, DESCRIPTION_SCHEMA
            )
            return str(result["description"]).strip()
        except JsonOutputError as exc:
            self.logger.error("WPF 控件描述 JSON 响应无效: %s", exc)
            return f"{message.wpf_tag} WPF 控件"

    def retrieve_candidates(
        self,
        description: str,
        wpf_tag: str,
        *,
        attributes: dict[str, Any] | None = None,
        semantic_references: list[dict[str, Any]] | None = None,
        source: str = "",
        k: int = 3,
    ) -> list[tuple[str, str, float]]:
        """返回组件名、检索文本和融合分数，供运行时与离线评测共用。"""
        if not self.knowledge_base:
            return []
        query = " ".join(
            [
                wpf_tag,
                description,
                json.dumps(attributes or {}, ensure_ascii=False),
                json.dumps(semantic_references or [], ensure_ascii=False),
                source[:2000],
            ]
        )
        lexical_scores = self.knowledge_base.lexical_scores(query)
        candidates = []
        query_embedding = self._embedding(query) if self.use_semantic_similarity else []
        for name in self.mui_components_index:
            aliases = self.knowledge_base.aliases_for(name)
            name_score = max(
                self._name_similarity(wpf_tag, alias) for alias in aliases
            )
            lexical_score = lexical_scores[name]
            if self.use_semantic_similarity:
                semantic_score = self._cosine(
                    query_embedding,
                    self._embedding(self.knowledge_base.search_text(name)),
                )
                score = 0.45 * name_score + 0.35 * lexical_score + 0.20 * semantic_score
            else:
                score = 0.55 * name_score + 0.45 * lexical_score
            candidates.append(
                (name, self.knowledge_base.search_text(name), round(score, 6))
            )
        return sorted(candidates, key=lambda item: (-item[2], item[0]))[:k]

    def _mapping_result(self, wpf_tag: str) -> tuple[list[str], list[str]] | None:
        mapping = self.wpf_to_mui_mapping.get(wpf_tag)
        if not mapping or not mapping.get("mui_component"):
            return None
        name = mapping["mui_component"]
        lines = []
        if self.knowledge_base and name in self.mui_components_index:
            lines.append(self.knowledge_base.render_document(name))
        if mapping.get("notes"):
            lines.append("WPF 映射说明：" + mapping["notes"])
        if mapping.get("usage_example"):
            lines.append(
                "映射配方：\n```tsx\n" + mapping["usage_example"] + "\n```"
            )
        return [name], ["\n\n".join(lines)]

    @message_handler
    async def handle_selection_request(
        self, message: MUISelectionRequest, ctx: MessageContext
    ) -> MUISelectionResponse:
        mapping = self._mapping_result(message.wpf_tag)
        if mapping:
            names, docs = mapping
            if not self.retrieval_enabled:
                docs = ["" for _ in names]
            return MUISelectionResponse(
                selected_components=names,
                docs=docs,
                retrieval_strategy="deterministic_mapping",
                confidence=1.0,
                candidate_scores=[1.0],
            )
        if not self.retrieval_enabled:
            return MUISelectionResponse(selected_components=[], docs=[])

        description = await self._generate_wpf_description(message)
        candidates = self.retrieve_candidates(
            description,
            message.wpf_tag,
            attributes=message.attributes,
            semantic_references=message.semantic_references,
            source=message.wpf_source,
            k=message.max_components,
        )
        if not candidates or candidates[0][2] < self.minimum_confidence:
            return MUISelectionResponse(
                selected_components=[],
                docs=[],
                retrieval_strategy="unresolved",
                confidence=candidates[0][2] if candidates else 0.0,
                candidate_scores=[item[2] for item in candidates],
                query_description=description,
            )
        names = [item[0] for item in candidates]
        return MUISelectionResponse(
            selected_components=names,
            docs=[self.knowledge_base.render_document(name) for name in names],
            retrieval_strategy="hybrid_rag",
            confidence=candidates[0][2],
            candidate_scores=[item[2] for item in candidates],
            query_description=description,
        )
