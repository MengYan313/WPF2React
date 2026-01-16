# -*- coding: utf-8 -*-
"""
MUI Component Selection Agent

负责根据 WPF 源代码智能选择合适的 MUI 组件。
"""

import json
from typing import Dict, Any, Optional
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import MUISelectionRequest, MUISelectionResponse


class MUISelectAgent(BaseMigrationAgent):
    """
    MUI 组件选择 Agent
    
    职责：
    1. 接收 WPF 组件源代码
    2. 使用 LLM 从 MUI 组件库中选择 1-3 个最合适的组件
    3. 读取选中组件的完整文档
    4. 返回组合后的 MUI 文档
    """
    
    def __init__(
        self,
        mui_json_path: str = "rag/mui/mui_components.json",
        mui_docs_dir: str = "rag/mui/components",
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化 MUI 选择 Agent
        
        Args:
            mui_json_path: MUI 组件索引 JSON 文件路径
            mui_docs_dir: MUI 组件文档目录
            llm_config: LLM 配置（默认使用 gpt-4o + JSON 模式）
        """
        # 初始化基类
        super().__init__(
            agent_type="MUISelectAgent",
            llm_config=llm_config or LLMConfig(
                model="gpt-4o",
                temperature=0,
                json_mode=True
            )
        )
        
        # MUI 组件库配置
        self.mui_json_path = Path(mui_json_path)
        self.mui_docs_dir = Path(mui_docs_dir)
        
        # 加载 MUI 组件索引
        self.mui_components_index = self._load_mui_components_index()
        
        # 系统提示词
        self.system_message = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """You are an expert in WPF to React/MUI migration.

Your task is to analyze WPF component source code and select 1-3 most suitable Material-UI (MUI) components that can be used to implement similar functionality in React.

Consider:
1. The UI structure and layout of the WPF component
2. The visual appearance and styling
3. The user interaction patterns
4. The data binding and state management

You must respond in JSON format with the following structure:
{
  "selected_components": ["ComponentName1", "ComponentName2", ...],
  "reasoning": "Brief explanation of why these components were selected"
}

Select 1-3 components. Use fewer components if the WPF component is simple."""
    
    def _load_mui_components_index(self) -> Dict[str, Any]:
        """加载 MUI 组件索引"""
        if not self.mui_json_path.exists():
            raise FileNotFoundError(f"MUI 组件索引文件不存在: {self.mui_json_path}")
        
        with open(self.mui_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @message_handler
    async def handle_selection_request(
        self, 
        message: MUISelectionRequest, 
        ctx: MessageContext
    ) -> MUISelectionResponse:
        """
        处理 MUI 组件选择请求
        
        Args:
            message: MUI 选择请求消息
            ctx: 消息上下文
        
        Returns:
            MUI 选择响应消息
        """
        # 1. 准备 MUI 组件列表
        components_info = self._prepare_components_info()
        
        # 2. 构建用户提示词
        user_prompt = self._build_user_prompt(
            wpf_source=message.wpf_source,
            wpf_tag=message.wpf_tag,
            components_info=components_info,
            max_components=message.max_components
        )
        
        # 3. 调用 LLM 选择组件
        response = await self.call_llm(
            system_message=self.system_message,
            user_message=user_prompt
        )
        
        # 4. 解析 JSON 响应
        try:
            # 清理可能的 markdown 代码块标记
            cleaned_response = response.strip()
            if cleaned_response.startswith("```"):
                # 移除开头的 ```json 或 ```
                lines = cleaned_response.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # 移除结尾的 ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned_response = '\n'.join(lines)
            
            result = json.loads(cleaned_response)
            selected_components = result.get("selected_components", [])
            reasoning = result.get("reasoning", "")
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM 返回的不是有效的 JSON: {e}\n响应: {response}")
        
        # 5. 读取选中组件的完整文档
        docs = self._read_components_docs(selected_components)
        
        # 6. 返回响应
        return MUISelectionResponse(
            selected_components=selected_components,
            docs=docs,
            reasoning=reasoning
        )
    
    def _prepare_components_info(self) -> str:
        """准备 MUI 组件信息摘要"""
        components_list = []
        
        for component in self.mui_components_index.get("components", []):
            name = component.get("name", "")
            description = component.get("description", "")
            
            if name and description:
                components_list.append(f"- **{name}**: {description}")
        
        return "\n".join(components_list)
    
    def _build_user_prompt(
        self,
        wpf_source: str,
        wpf_tag: str,
        components_info: str,
        max_components: int
    ) -> str:
        """构建用户提示词"""
        return f"""# Task

Analyze the following WPF component and select the most suitable MUI components for migration.

## WPF Component

**Tag**: {wpf_tag}

**Source Code**:
```xaml
{wpf_source}
```

## Available MUI Components

{components_info}

## Requirements

- Select **{max_components} or fewer** MUI components
- Choose components that best match the WPF component's functionality
- Provide clear reasoning for your selection

## Response Format

Respond in JSON format:
{{
  "selected_components": ["Component1", "Component2"],
  "reasoning": "Explanation of why these components were selected"
}}
"""
    
    def _read_components_docs(self, component_names: list) -> str:
        """
        读取多个 MUI 组件的完整文档
        
        Args:
            component_names: MUI 组件名称列表
        
        Returns:
            合并后的文档字符串
        """
        docs = []
        
        for name in component_names:
            doc_path = self.mui_docs_dir / f"{name}.md"
            
            if doc_path.exists():
                try:
                    with open(doc_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    docs.append(f"# {name} Component\n\n{content}")
                except Exception as e:
                    docs.append(f"# {name} Component\n\nError reading documentation: {e}")
            else:
                docs.append(f"# {name} Component\n\nDocumentation file not found: {doc_path}")
        
        return "\n\n" + "="*80 + "\n\n".join(docs)
