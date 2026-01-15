# -*- coding: utf-8 -*-
"""
MUI 组件选择器模块

负责根据 WPF 源代码，使用 LLM 从 MUI 组件库中选择最合适的组件。
"""

import json
from typing import List, Optional, Dict, Any
from pathlib import Path

from ..llm import LLMClient, LLMConfig


class MUIComponentSelector:
    """
    MUI 组件智能选择器
    
    根据 WPF 组件源代码，使用 LLM 分析并选择 1-3 个最合适的 MUI 组件。
    然后读取选中组件的完整文档，用于后续的组件迁移。
    """
    
    def __init__(
        self,
        mui_json_path: str = "rag/mui/mui_components.json",
        mui_docs_dir: str = "rag/mui/components",
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化 MUI 组件选择器
        
        Args:
            mui_json_path: MUI 组件索引 JSON 文件路径
            mui_docs_dir: MUI 组件文档目录
            llm_config: LLM 配置（用于组件选择）
        """
        self.mui_json_path = Path(mui_json_path)
        self.mui_docs_dir = Path(mui_docs_dir)
        
        # 用于组件选择的 LLM 配置（使用 JSON 模式）
        self.llm_config = llm_config or LLMConfig(
            model="gpt-4o-mini",  # 组件选择任务较简单，使用 mini 版本
            temperature=0,
            json_mode=True
        )
        self.llm_client = LLMClient(self.llm_config)
        
        # 加载 MUI 组件索引
        self.mui_components_index = self._load_mui_components_index()
    
    def _load_mui_components_index(self) -> Dict[str, Any]:
        """
        加载 MUI 组件索引 JSON 文件
        
        Returns:
            MUI 组件索引数据
        """
        if not self.mui_json_path.exists():
            raise FileNotFoundError(f"MUI components JSON not found: {self.mui_json_path}")
        
        with open(self.mui_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    async def select_mui_components(
        self,
        wpf_source: str,
        wpf_tag: str = "Unknown",
        max_components: int = 3
    ) -> List[str]:
        """
        根据 WPF 源代码选择合适的 MUI 组件（异步）
        
        Args:
            wpf_source: WPF 组件源代码
            wpf_tag: WPF 组件标签名称（例如 "Grid", "Button"）
            max_components: 最多选择的组件数量（1-3）
            
        Returns:
            选中的 MUI 组件名称列表
        """
        # 构建提示词
        system_prompt = self._build_selection_system_prompt()
        user_prompt = self._build_selection_user_prompt(
            wpf_source=wpf_source,
            wpf_tag=wpf_tag,
            max_components=max_components
        )
        
        # 调用 LLM
        response = await self.llm_client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 解析 JSON 响应
        try:
            result = json.loads(response)
            selected_components = result.get("selected_components", [])
            
            # 验证选择的组件是否存在
            valid_components = []
            all_component_names = {comp["name"] for comp in self.mui_components_index.get("components", [])}
            
            for comp_name in selected_components:
                if comp_name in all_component_names:
                    valid_components.append(comp_name)
                else:
                    print(f"  ⚠ 警告: LLM 选择的组件 '{comp_name}' 不在 MUI 组件库中，已忽略")
            
            return valid_components[:max_components]  # 确保不超过最大数量
            
        except json.JSONDecodeError as e:
            print(f"  ⚠ 警告: 无法解析 LLM 响应为 JSON: {e}")
            return []
    
    def _build_selection_system_prompt(self) -> str:
        """
        构建组件选择任务的系统提示词
        
        Returns:
            系统提示词字符串
        """
        return """You are an expert in WPF to React/MUI migration.

Your task is to analyze WPF component source code and select 1-3 most suitable Material-UI (MUI) components that can be used to implement similar functionality in React.

Consider:
1. The UI structure and layout of the WPF component
2. The visual appearance and styling
3. The user interaction patterns
4. The data binding and state management

You will be provided with:
- WPF component source code (XAML)
- A list of available MUI components with descriptions

You must respond in JSON format with the following structure:
{
  "selected_components": ["ComponentName1", "ComponentName2", ...],
  "reasoning": "Brief explanation of why these components were selected"
}

Select 1-3 components. Use fewer components if the WPF component is simple.
"""
    
    def _build_selection_user_prompt(
        self,
        wpf_source: str,
        wpf_tag: str,
        max_components: int
    ) -> str:
        """
        构建组件选择任务的用户提示词
        
        Args:
            wpf_source: WPF 源代码
            wpf_tag: WPF 标签名称
            max_components: 最多选择的组件数量
            
        Returns:
            用户提示词字符串
        """
        # 构建 MUI 组件列表（仅包含名称和描述，不包含代码示例以节省 token）
        mui_components_info = []
        for comp in self.mui_components_index.get("components", []):
            mui_components_info.append({
                "name": comp["name"],
                "description": comp["description"]
            })
        
        mui_components_json = json.dumps(mui_components_info, indent=2, ensure_ascii=False)
        
        return f"""# WPF Component to Migrate

**WPF Component Tag:** {wpf_tag}

**WPF Source Code:**
```xaml
{wpf_source}
```

# Available MUI Components

{mui_components_json}

# Task

Analyze the WPF component above and select {max_components} most suitable MUI component(s) from the available list.

Return your selection in JSON format:
{{
  "selected_components": ["ComponentName1", "ComponentName2", ...],
  "reasoning": "Brief explanation"
}}
"""
    
    async def get_mui_docs_for_wpf(
        self,
        wpf_source: str,
        wpf_tag: str = "Unknown"
    ) -> str:
        """
        根据 WPF 源代码获取相关的 MUI 组件文档（完整流程）（异步）
        
        Args:
            wpf_source: WPF 组件源代码
            wpf_tag: WPF 组件标签名称
            
        Returns:
            组合后的 MUI 组件文档字符串
        """
        # 1. 使用 LLM 选择 MUI 组件
        selected_components = await self.select_mui_components(
            wpf_source=wpf_source,
            wpf_tag=wpf_tag
        )
        
        if not selected_components:
            print(f"  ⚠ 警告: 未能为 WPF 组件 '{wpf_tag}' 选择合适的 MUI 组件")
            return ""
        
        print(f"  ✓ 为 '{wpf_tag}' 选择了 MUI 组件: {', '.join(selected_components)}")
        
        # 2. 读取选中组件的完整文档
        docs_parts = []
        for comp_name in selected_components:
            doc_content = self._read_component_doc(comp_name)
            if doc_content:
                docs_parts.append(f"# MUI Component: {comp_name}\n\n{doc_content}")
        
        return "\n\n" + "="*80 + "\n\n".join(docs_parts)
    
    def _read_component_doc(self, component_name: str) -> Optional[str]:
        """
        读取指定 MUI 组件的 Markdown 文档
        
        Args:
            component_name: MUI 组件名称（例如 "Button"）
            
        Returns:
            文档内容字符串，如果文件不存在则返回 None
        """
        doc_file = self.mui_docs_dir / f"{component_name}.md"
        
        if not doc_file.exists():
            print(f"  ⚠ 警告: MUI 组件文档不存在: {doc_file}")
            return None
        
        try:
            with open(doc_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"  ⚠ 警告: 读取 MUI 组件文档失败 ({component_name}): {e}")
            return None

