# -*- coding: utf-8 -*-
"""
MUI Component Selection Agent

负责根据 WPF 源代码智能选择合适的 MUI 组件。
采用两步选择策略：
1. 直接映射：检查 WPF 到 MUI 映射文件，如果存在直接返回
2. 相似度匹配：基于描述语义相似度和名称相似度筛选最相似的 MUI 组件

使用语义相似度模型（sentence-transformers）计算描述相似度，提高匹配准确性。
"""

import json
import re
from collections import OrderedDict
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import MUISelectionRequest, MUISelectionResponse

# 尝试导入语义相似度库（可选）
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class MUISelectAgent(BaseMigrationAgent):
    """
    MUI 组件选择 Agent
    
    职责：
    1. 接收 WPF 组件源代码
    2. 检查直接映射（WPF 到 MUI 映射文件）
    3. 如果没有映射，生成 WPF 组件的标准化描述
    4. 基于相似度筛选最相似的 MUI 组件
    5. 返回组件文档（name, description, usage_example）
    """
    
    def __init__(
        self,
        mui_json_path: str = "rag/mui/mui_components.json",
        wpf_to_mui_mapping_path: str = "rag/mui/wpf_to_mui_mapping.json",
        llm_config: Optional[LLMConfig] = None,
        output_base_dir: str = "outputs",
        use_semantic_similarity: bool = True,
        semantic_model: str = "sentence-transformers",  # "sentence-transformers" 或 "openai"
        semantic_model_name: str = "all-MiniLM-L6-v2"  # sentence-transformers 模型名称
    ):
        """
        初始化 MUI 选择 Agent
        
        Args:
            mui_json_path: MUI 组件索引 JSON 文件路径
            wpf_to_mui_mapping_path: WPF 到 MUI 映射 JSON 文件路径
            llm_config: LLM 配置（默认使用 gpt-4o，使用标记格式）
            output_base_dir: 输出基础目录（用于日志配置）
            use_semantic_similarity: 是否使用语义相似度（默认 True）
            semantic_model: 语义相似度模型类型，"sentence-transformers" 或 "openai"
            semantic_model_name: sentence-transformers 模型名称（默认 all-MiniLM-L6-v2）
        """
        # 初始化基类
        super().__init__(
            agent_type="MUISelectAgent",
            llm_config=llm_config or LLMConfig(
                model="gpt-4o",
                temperature=0,
                json_mode=False  # 使用标记格式，不使用 JSON 模式
            ),
            output_base_dir=output_base_dir
        )
        
        # MUI 组件库配置
        self.mui_json_path = Path(mui_json_path)
        self.wpf_to_mui_mapping_path = Path(wpf_to_mui_mapping_path)
        
        # 加载 MUI 组件索引
        self.mui_components_index = self._load_mui_components_index()
        
        # 加载 WPF 到 MUI 映射
        self.wpf_to_mui_mapping = self._load_wpf_to_mui_mapping()
        
        # 语义相似度配置
        self.use_semantic_similarity = use_semantic_similarity
        self.semantic_model_type = semantic_model
        self.semantic_model_name = semantic_model_name
        self._embedding_model = None
        # 嵌入向量缓存：用 OrderedDict 实现有界 LRU，防止长时间运行时无限增长。
        # 超出上限时淘汰最久未用项；同一文本的嵌入是确定的，淘汰后重新计算
        # 结果一致，故仅影响内存占用、不改变选择结果。
        self._embedding_cache: "OrderedDict[str, List[float]]" = OrderedDict()
        self._embedding_cache_max_size = 2048
        
        # 初始化语义相似度模型
        if self.use_semantic_similarity:
            self._init_semantic_model()
    
    def _load_mui_components_index(self) -> Dict[str, Any]:
        """加载 MUI 组件索引"""
        if not self.mui_json_path.exists():
            raise FileNotFoundError(f"MUI 组件索引文件不存在: {self.mui_json_path}")
        
        with open(self.mui_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_wpf_to_mui_mapping(self) -> Dict[str, Any]:
        """加载 WPF 到 MUI 映射"""
        if not self.wpf_to_mui_mapping_path.exists():
            self.logger.warning(f"WPF 到 MUI 映射文件不存在: {self.wpf_to_mui_mapping_path}，将跳过映射检查")
            return {}
        
        with open(self.wpf_to_mui_mapping_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _init_semantic_model(self):
        """
        初始化语义相似度模型
        
        默认使用 sentence-transformers 的 all-MiniLM-L6-v2 模型。
        模型会在首次使用时自动下载到本地缓存目录（~/.cache/huggingface/）。
        """
        if self.semantic_model_type == "sentence-transformers":
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                raise ImportError(
                    "sentence-transformers 未安装，无法使用语义相似度。"
                    "安装命令: pip install sentence-transformers"
                )
            
            # 使用指定的模型（默认 all-MiniLM-L6-v2）
            # 模型会在首次使用时自动下载到本地
            # 缓存位置：~/.cache/huggingface/hub/models--sentence-transformers--{model_name}/
            model_name = self.semantic_model_name
            self.logger.info(f"正在加载语义相似度模型: {model_name}（首次使用会自动下载）")
            self._embedding_model = SentenceTransformer(model_name)
            self.logger.info(f"✓ 语义相似度模型加载成功: {model_name}")
        
        elif self.semantic_model_type == "openai":
            if not OPENAI_AVAILABLE:
                raise ImportError(
                    "openai 库未安装，无法使用语义相似度。"
                    "安装命令: pip install openai"
                )
            
            # OpenAI embeddings 不需要预加载模型，使用时直接调用 API
            if not self.llm_config or not self.llm_config.api_key:
                raise ValueError("OpenAI API key 未配置，无法使用语义相似度")
    
    def _get_embedding(self, text: str) -> List[float]:
        """
        获取文本的嵌入向量（带缓存）
        
        Args:
            text: 输入文本
            
        Returns:
            嵌入向量
        """
        # 检查缓存（命中则刷新为最近使用）
        if text in self._embedding_cache:
            self._embedding_cache.move_to_end(text)
            return self._embedding_cache[text]
        
        embedding = None
        
        if self.semantic_model_type == "sentence-transformers" and self._embedding_model:
            # 使用 sentence-transformers
            embedding = self._embedding_model.encode(text, convert_to_numpy=False).tolist()
        
        elif self.semantic_model_type == "openai" and self.llm_config:
            # 使用 OpenAI embeddings
            import openai
            client = openai.OpenAI(
                api_key=self.llm_config.api_key,
                base_url=self.llm_config.base_url
            )
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            embedding = response.data[0].embedding
        
        # 缓存结果（有界 LRU：超出上限淘汰最久未用项）
        if embedding:
            self._embedding_cache[text] = embedding
            self._embedding_cache.move_to_end(text)
            if len(self._embedding_cache) > self._embedding_cache_max_size:
                self._embedding_cache.popitem(last=False)

        return embedding
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度
        
        Args:
            vec1: 第一个向量
            vec2: 第二个向量
            
        Returns:
            余弦相似度 (0-1)
        """
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        cosine_sim = dot_product / (magnitude1 * magnitude2)
        # 归一化到 0-1（余弦相似度范围是 -1 到 1）
        return (cosine_sim + 1) / 2
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的语义相似度（使用嵌入向量）
        
        Args:
            text1: 第一个文本
            text2: 第二个文本
            
        Returns:
            语义相似度分数 (0-1)
        """
        embedding1 = self._get_embedding(text1)
        embedding2 = self._get_embedding(text2)
        
        if not embedding1 or not embedding2:
            raise ValueError("无法获取文本嵌入向量，语义相似度计算失败")
        
        return self._cosine_similarity(embedding1, embedding2)
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        计算两个组件名称的相似度
        
        使用多种策略：
        1. 完全匹配（忽略大小写）
        2. 包含关系（一个名称包含另一个）
        3. 词级相似度（拆分驼峰命名）
        4. 字符级相似度（Levenshtein距离的简化版本）
        
        Args:
            name1: 第一个组件名称（如 "TextBox"）
            name2: 第二个组件名称（如 "TextField"）
            
        Returns:
            相似度分数 (0-1)
        """
        name1_lower = name1.lower().strip()
        name2_lower = name2.lower().strip()
        
        # 1. 完全匹配
        if name1_lower == name2_lower:
            return 1.0
        
        # 2. 包含关系（双向检查）
        if name1_lower in name2_lower or name2_lower in name1_lower:
            # 计算包含比例
            shorter = min(len(name1_lower), len(name2_lower))
            longer = max(len(name1_lower), len(name2_lower))
            return shorter / longer if longer > 0 else 0.0
        
        # 3. 拆分驼峰命名，计算词级相似度
        def split_camel_case(name: str) -> List[str]:
            """拆分驼峰命名"""
            # 匹配大写字母开头的单词或连续的小写字母
            words = re.findall(r'[A-Z][a-z]*|[a-z]+', name)
            return [w.lower() for w in words if w]
        
        words1 = split_camel_case(name1)
        words2 = split_camel_case(name2)
        
        if words1 and words2:
            # 计算词级相似度
            words1_set = set(words1)
            words2_set = set(words2)
            intersection = words1_set & words2_set
            union = words1_set | words2_set
            
            if union:
                word_similarity = len(intersection) / len(union)
            else:
                word_similarity = 0.0
        
            # 如果词级相似度较高，直接返回
            if word_similarity > 0.3:
                return word_similarity
        
        # 4. 字符级相似度（简化的编辑距离）
        # 计算共同字符的比例
        chars1 = set(name1_lower)
        chars2 = set(name2_lower)
        
        if chars1 and chars2:
            intersection = chars1 & chars2
            union = chars1 | chars2
            char_similarity = len(intersection) / len(union) if union else 0.0
        else:
            char_similarity = 0.0
        
        # 返回词级和字符级的加权平均（如果词级相似度可用）
        if words1 and words2:
            return (word_similarity * 0.7 + char_similarity * 0.3)
        else:
            return char_similarity
    
    async def _generate_wpf_description(self, wpf_source: str, wpf_tag: str) -> str:
        """
        步骤1: 生成 WPF 组件的标准化描述
        
        Args:
            wpf_source: WPF 源代码
            wpf_tag: WPF 标签名
            
        Returns:
            标准化的组件描述
        """
        system_prompt = """You are an expert in WPF UI components.

Your task is to analyze WPF component source code and write a concise description following the Material-UI documentation style.

## Description Style Guidelines

Write descriptions that are:
1. **Concise and clear** - One or two sentences maximum
2. **Focus on purpose** - Describe what the component does, not how it's implemented
3. **User-centric** - Describe from the user's perspective
4. **Functional** - Highlight the main use case and functionality

## Examples from Material-UI

Good examples:
- "Buttons allow users to take actions, and make choices, with a single tap."
- "Text Fields let users enter and edit text."
- "The App Bar displays information and actions relating to the current screen."
- "Checkboxes allow users to select one or more items from a set."
- "Cards contain content and actions about a single subject."

## Output Format

**Output your response wrapped in `[Description]` and `[/Description]` tags:**

[Description]
A concise, clear description of the WPF component following the style above
[/Description]

**Important**: Do NOT use markdown code blocks (```). Use the `[Description]` and `[/Description]` tags instead.
"""
        
        user_prompt = f"""Analyze the following WPF component and write a description in Material-UI style.

[WPF Tag]
{wpf_tag}
[/WPF Tag]

[WPF Source Code]
{wpf_source[:1000]}
[/WPF Source Code]

Write a concise description (1-2 sentences) following the Material-UI style."""
        
        response = await self.call_llm(
            system_message=system_prompt,
            user_message=user_prompt
        )
        
        # 使用统一的标记提取工具
        from src.migration.utils import extract_tag_content
        return extract_tag_content(response, "Description", response.strip(), self.logger)
    
    def _find_top_k_similar_components(
        self, 
        wpf_description: str, 
        wpf_tag: str,
        k: int = 5
    ) -> List[Tuple[str, str, float]]:
        """
        步骤2: 基于描述语义相似度和名称相似度找出 Top K 个 MUI 组件
        
        结合两种相似度：
        1. 描述语义相似度：使用嵌入向量计算 WPF 组件描述 vs MUI 组件描述的语义相似度（权重 0.5）
        2. 名称相似度：WPF 组件名称 vs MUI 组件名称的字符串相似度（权重 0.5）
        
        Args:
            wpf_description: WPF 组件描述
            wpf_tag: WPF 组件标签名（如 "TextBox", "Button"）
            k: 返回前 K 个最相似的组件
            
        Returns:
            [(组件名, 描述, 综合相似度分数), ...] 列表
        """
        similarities = []
        
        # mui_components_index 现在是以组件名为 key 的字典
        for mui_name, component in self.mui_components_index.items():
            mui_description = component.get("description", "")
            
            if mui_name and mui_description:
                # 计算描述相似度
                desc_similarity = self._calculate_text_similarity(
                    wpf_description, 
                    mui_description
                )
                
                # 计算名称相似度
                name_similarity = self._calculate_name_similarity(
                    wpf_tag,
                    mui_name
                )
                
                # 综合相似度（各0.5权重）
                combined_similarity = (desc_similarity * 0.5 + name_similarity * 0.5)
                
                similarities.append((mui_name, mui_description, combined_similarity))
        
        # 按综合相似度降序排序，取前 K 个
        similarities.sort(key=lambda x: x[2], reverse=True)
        return similarities[:k]
    
    
    def _get_mapping_result(self, wpf_tag: str) -> Optional[Tuple[List[str], List[str]]]:
        """
        检查 WPF 组件是否在映射文件中存在
        
        Args:
            wpf_tag: WPF 组件标签名
        
        Returns:
            如果找到映射，返回 (组件名列表, 文档列表)，否则返回 None
        """
        if not self.wpf_to_mui_mapping:
            return None
        
        if wpf_tag not in self.wpf_to_mui_mapping:
            return None
        
        mapping = self.wpf_to_mui_mapping[wpf_tag]
        mui_component = mapping.get("mui_component", "")
        usage_example = mapping.get("usage_example", "")
        notes = mapping.get("notes", "")
        
        if not mui_component:
            return None
        
        # 组合 usage_example 和 notes
        combined_doc = ""
        if notes:
            combined_doc += f"## Notes\n{notes}\n\n"
        if usage_example:
            combined_doc += f"## Usage Example\n```typescript\n{usage_example}\n```"
        
        # 返回列表格式（即使只有一个组件）
        return ([mui_component], [combined_doc.strip()])
    
    @message_handler
    async def handle_selection_request(
        self, 
        message: MUISelectionRequest, 
        ctx: MessageContext
    ) -> MUISelectionResponse:
        """
        处理 MUI 组件选择请求
        
        首先检查映射文件，如果找到直接返回；否则使用三步选择策略。
        
        Args:
            message: MUI 选择请求消息
            ctx: 消息上下文
        
        Returns:
            MUI 选择响应消息
        """
        # 预检查：查找映射文件中的映射
        mapping_result = self._get_mapping_result(message.wpf_tag)
        if mapping_result is not None:
            selected_components, docs = mapping_result
            self.logger.debug(f"映射 {message.wpf_tag} -> {selected_components}")
            return MUISelectionResponse(
                selected_components=selected_components,
                docs=docs
            )
        
        # 如果没有映射，使用相似度匹配
        # 步骤1: 生成 WPF 组件的标准化描述（用于相似度计算）
        wpf_description = await self._generate_wpf_description(
            wpf_source=message.wpf_source,
            wpf_tag=message.wpf_tag
        )
        
        # 步骤2: 基于描述语义相似度和名称相似度找出 Top K MUI 组件
        # K 值设为 max_components，直接取前几个最相似的组件
        top_candidates = self._find_top_k_similar_components(
            wpf_description=wpf_description,
            wpf_tag=message.wpf_tag,
            k=message.max_components
        )
        
        # 步骤3: 直接从相似度匹配结果中选择前 max_components 个组件
        # 按相似度分数从高到低，取前 max_components 个
        selected_components = [name for name, _, _ in top_candidates[:message.max_components]]
        
        # 如果相似度匹配没有结果，至少返回一个默认组件
        if not selected_components:
            self.logger.warning(f"相似度匹配未找到合适的组件，使用默认组件")
            selected_components = ["Box"]  # 默认使用 Box 组件
        
        # 4. 读取选中组件的使用示例
        docs = self._read_components_docs(selected_components)
        
        # 5. 返回响应
        return MUISelectionResponse(
            selected_components=selected_components,
            docs=docs
        )
    
    def _read_components_docs(self, component_names: list) -> List[str]:
        """
        读取多个 MUI 组件的使用示例（从 JSON 索引中提取）
        
        Args:
            component_names: MUI 组件名称列表
        
        Returns:
            使用示例列表，与 component_names 一一对应
        """
        usage_examples = []
        
        # mui_components_index 现在是以组件名为 key 的字典
        for name in component_names:
            if name in self.mui_components_index:
                component = self.mui_components_index[name]
                usage_example = component.get("usage_example", "")
                usage_examples.append(usage_example)
            else:
                # 如果组件不存在，返回空字符串
                usage_examples.append("")
        
        return usage_examples
