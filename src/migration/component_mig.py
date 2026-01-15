# -*- coding: utf-8 -*-
"""
WPF 单个组件到 React 组件迁移模块

负责单个 WPF 组件的迁移，使用 LLM 进行智能转换。
"""

from typing import Dict, Optional, Any, List
from pathlib import Path

from ..llm import LLMClient, LLMConfig, parse_json_response


class ComponentMigrator:
    """
    单个 WPF 组件迁移器
    
    负责调用 LLM 将单个 WPF 组件转换为 React + MUI 组件。
    """
    
    def __init__(self, llm_config: Optional[LLMConfig] = None):
        """
        初始化组件迁移器
        
        Args:
            llm_config: LLM 配置，默认使用 gpt-4o + JSON 模式
        """
        self.llm_config = llm_config or LLMConfig(
            model="gpt-4o",
            temperature=0,
            json_mode=True
        )
        self.llm_client = LLMClient(self.llm_config)
    
    def _build_migration_prompt(
        self,
        wpf_source: str,
        wpf_dependencies: Optional[str],
        children_react_code: Optional[str],
        mui_components_docs: Optional[str]
    ) -> str:
        """
        构建迁移 prompt
        
        Args:
            wpf_source: WPF 组件源代码
            wpf_dependencies: 该组件依赖的其他 WPF 代码
            children_react_code: 子节点已完成的 React 代码
            mui_components_docs: MUI 组件文档（暂时为空）
            
        Returns:
            完整的 prompt 字符串
        """
        prompt_parts = [
            "# Task: Migrate WPF Component to React with Material-UI",
            "",
            "You are an expert in migrating WPF applications to React with Material-UI (MUI).",
            "Your task is to convert the given WPF XAML component to a React component using MUI.",
            "",
            "## Input Information",
            "",
            "### 1. WPF Source Code",
            "```xml",
            wpf_source.strip(),
            "```",
        ]
        
        if wpf_dependencies:
            prompt_parts.extend([
                "",
                "### 2. WPF Dependencies",
                "The following WPF code is used by this component:",
                "```xml",
                wpf_dependencies.strip(),
                "```",
            ])
        
        if children_react_code:
            prompt_parts.extend([
                "",
                "### 3. Migrated Child Components",
                "The child components have already been migrated to React. Use them in your implementation:",
                "```tsx",
                children_react_code.strip(),
                "```",
            ])
        
        if mui_components_docs:
            prompt_parts.extend([
                "",
                "### 4. MUI Components Documentation",
                "",
                mui_components_docs,
            ])
        
        prompt_parts.extend([
            "",
            "## Requirements",
            "",
            "1. Convert the WPF component to a functional React component using TypeScript",
            "2. Use Material-UI (MUI) components to replicate the UI",
            "3. Preserve the original functionality and layout as much as possible",
            "4. Handle WPF-specific features (data binding, commands, etc.) with React equivalents (useState, useCallback, etc.)",
            "5. Add proper TypeScript types and interfaces",
            "6. Include necessary imports",
            "7. Add brief comments for complex logic",
            "",
            "## Output Format",
            "",
            "Return a JSON object with the following structure:",
            "```json",
            "{",
            '  "component_name": "ComponentName",',
            '  "description": "Brief description of what this component does",',
            '  "imports": ["import statements as array of strings"],',
            '  "interfaces": "TypeScript interfaces/types if needed (empty string if not needed)",',
            '  "react_code": "The complete React component code",',
            '  "usage_example": "Example of how to use this component",',
            '  "migration_notes": "Any important notes about the migration"',
            "}",
            "```",
            "",
            "Make sure the JSON is valid and properly escaped."
        ])
        
        return "\n".join(prompt_parts)
    
    async def migrate(
        self,
        wpf_source: str,
        wpf_dependencies: Optional[str] = None,
        children_react_code: Optional[str] = None,
        mui_components_docs: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        迁移单个 WPF 组件到 React（异步）
        
        Args:
            wpf_source: WPF 组件源代码
            wpf_dependencies: 该组件依赖的其他 WPF 代码
            children_react_code: 子节点已完成的 React 代码
            mui_components_docs: MUI 组件文档（暂时为空）
            
        Returns:
            包含迁移结果的字典：
            {
                "component_name": "组件名称",
                "description": "组件描述",
                "imports": ["导入语句列表"],
                "interfaces": "类型定义",
                "react_code": "React 组件代码",
                "usage_example": "使用示例",
                "migration_notes": "迁移说明"
            }
            
        Raises:
            ValueError: 如果 LLM 返回的结果无法解析或缺少必需字段
        """
        # 构建 prompt
        prompt = self._build_migration_prompt(
            wpf_source=wpf_source,
            wpf_dependencies=wpf_dependencies,
            children_react_code=children_react_code,
            mui_components_docs=mui_components_docs
        )
        
        # 调用 LLM（异步，JSON 模式）
        response = await self.llm_client.chat(
            prompt=prompt,
            json_mode=True
        )
        
        # 解析 JSON 响应
        result = parse_json_response(response)
        
        if not result:
            raise ValueError(f"Failed to parse LLM response as JSON: {response[:200]}")
        
        # 验证必需字段
        required_fields = ["component_name", "react_code"]
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Missing required field '{field}' in LLM response")
        
        return result
