# -*- coding: utf-8 -*-
"""
Page Migration Agent

负责协调整个页面的迁移，管理组件树的递归迁移过程。
使用消息传递与其他 Agent 通信（Autogen 最佳实践）。
"""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from autogen_core import MessageContext, message_handler, AgentId

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import (
    PageMigrationRequest, 
    PageMigrationResponse,
    MUISelectionRequest,
    MUISelectionResponse,
    ComponentMigrationRequest,
    ComponentMigrationResponse,
    PageAssemblyRequest,
    PageAssemblyResponse
)


class PageMigrateAgent(BaseMigrationAgent):
    """
    页面迁移 Agent
    
    职责：
    1. 加载和解析 control JSON 文件
    2. 递归遍历组件树（从叶子节点向上）
    3. 通过消息传递协调 MUISelectAgent 和 ComponentMigrateAgent
    4. 管理迁移结果的缓存和输出
    5. 生成最终的 React 页面代码
    """
    
    def __init__(
        self,
        project_name: str,
        output_base_dir: str = "outputs",
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化页面迁移 Agent
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
            llm_config: LLM 配置（用于页面整合阶段）
        """
        # 初始化基类（需要 LLM 进行页面整合）
        super().__init__(
            agent_type="PageMigrateAgent",
            llm_config=llm_config or LLMConfig(
                model="gpt-4o",
                temperature=0,
                json_mode=False  # 页面整合不需要 JSON 模式
            ),
            output_base_dir=output_base_dir
        )
        
        # 项目配置
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        
        # 迁移缓存（使用节点路径作为唯一标识）
        self.migration_cache: Dict[str, Dict[str, Any]] = {}
        
        # 目录路径
        self.dependency_dir = self.output_base_dir / project_name / "dependency"
        self.migration_dir = self.output_base_dir / project_name / "migration"
    
    @message_handler
    async def handle_page_migration_request(
        self, 
        message: PageMigrationRequest, 
        ctx: MessageContext
    ) -> PageMigrationResponse:
        """
        处理页面迁移请求
        
        Args:
            message: 页面迁移请求消息
            ctx: 消息上下文
        
        Returns:
            页面迁移响应消息
        """
        try:
            # 清空缓存
            self.migration_cache.clear()
            
            # 确定 control JSON 文件路径
            if message.control_json_path:
                control_json_path = message.control_json_path
            else:
                # 使用页面名称构建路径
                control_json_path = str(
                    self.dependency_dir / f"control_{message.page_name}.json"
                )
            
            # 执行迁移
            result = await self._migrate_page_from_control_json(
                control_json_path=control_json_path,
                ctx=ctx
            )
            
            # 生成输出
            output_path = self._generate_output(
                page_name=message.page_name,
                result=result,
                output_dir=message.output_dir
            )
            
            return PageMigrationResponse(
                page_name=message.page_name,
                total_components=result.get("total_components", 0),
                migrated_components=len(self.migration_cache),
                output_path=output_path,
                success=True
            )
            
        except Exception as e:
            return PageMigrationResponse(
                page_name=message.page_name,
                total_components=0,
                migrated_components=0,
                output_path="",
                success=False,
                error=str(e)
            )
    
    async def _migrate_page_from_control_json(
        self,
        control_json_path: str,
        ctx: MessageContext
    ) -> Dict[str, Any]:
        """
        从 control JSON 文件迁移整个页面
        
        Args:
            control_json_path: control JSON 文件路径
            ctx: 消息上下文（用于 Agent 通信）
        
        Returns:
            迁移结果字典
        """
        # 1. 加载 control JSON
        control_data = self._load_control_json(control_json_path)
        
        # 2. 提取根节点和树结构
        # 注意：字段名为 "controls"（不是 "tree"）和 "control_count"（不是 "total"）
        tree = control_data.get("controls", {})
        total_components = control_data.get("control_count", 0)
        root_tag = tree.get("tag", "") if tree else ""
        page_name = Path(control_json_path).stem.replace("control_", "")
        
        if not tree:
            raise ValueError(f"control JSON 中没有 controls 结构: {control_json_path}")
        
        # 日志：页面迁移开始
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"开始迁移页面: {page_name}")
        self.logger.debug(f"  根标签: <{root_tag}>")
        self.logger.debug(f"  总组件数: {total_components}")
        self.logger.debug(f"  迁移策略: 自底向上递归")
        self.logger.info(f"{'='*80}\n")
        
        # 3. 递归迁移整个组件树（组件迁移阶段）
        root_result = await self._migrate_node_recursive(
            node=tree,
            node_path="root",
            wpf_dependencies="",
            ctx=ctx
        )
        
        # 日志：组件迁移完成
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"组件迁移完成: {page_name}")
        self.logger.debug(f"  已迁移组件数: {len(self.migration_cache)}")
        self.logger.debug(f"  根组件: {root_result.get('component_name', 'Unknown')}")
        self.logger.info(f"{'='*80}\n")
        
        # 4. 页面整合阶段：将根组件整合成完整页面
        self.logger.info("开始页面整合...")
        page_source = tree.get("source_code", "")
        assembled_page = await self._assemble_page(
            page_name=page_name,
            page_source=page_source,
            root_result=root_result
        )
        
        # 用整合后的页面代码替换根组件的 react_code
        root_result["react_code"] = assembled_page["page_code"]
        root_result["description"] = assembled_page["page_description"]
        root_result["migration_notes"] = assembled_page["assembly_notes"]
        
        self.logger.info("页面整合完成")
        self.logger.info(f"{'='*80}\n")
        
        return {
            "page_name": Path(control_json_path).stem.replace("control_", ""),
            "root_tag": root_tag,
            "total_components": total_components,
            "root_component": root_result
        }
    
    async def _migrate_node_recursive(
        self,
        node: Dict[str, Any],
        node_path: str,
        wpf_dependencies: str,
        ctx: MessageContext
    ) -> Dict[str, Any]:
        """
        递归迁移节点及其子节点
        
        Args:
            node: 节点数据
            node_path: 节点路径（唯一标识）
            wpf_dependencies: WPF 依赖代码
            ctx: 消息上下文（用于 Agent 通信）
        
        Returns:
            迁移结果字典
        """
        # 检查缓存
        if node_path in self.migration_cache:
            return self.migration_cache[node_path]
        
        # 提取节点信息
        wpf_tag = node.get("tag", "")
        xaml_code = node.get("source_code", "")  # 注意：字段名为 "source_code"
        children = node.get("children", [])
        
        # 日志：开始处理节点
        indent = "  " * node_path.count(".")
        self.logger.debug(f"{indent}[{node_path}] <{wpf_tag}> (子组件: {len(children)})")
        
        # 1. 先递归迁移所有子节点
        child_results = []
        
        for idx, child in enumerate(children):
            child_path = f"{node_path}.{idx}"
            child_result = await self._migrate_node_recursive(
                node=child,
                node_path=child_path,
                wpf_dependencies=wpf_dependencies,
                ctx=ctx
            )
            child_results.append(child_result)
        
        # 2. 合并子组件的 React 代码
        child_react_code = self._merge_child_react_code(child_results)
        
        # 3. 通过消息传递请求 MUISelectAgent 选择组件
        mui_request = MUISelectionRequest(
            wpf_source=xaml_code,
            wpf_tag=wpf_tag,
            max_components=3
        )
        
        # 发送消息到 MUISelectAgent
        mui_response = await self.send_message(
            message=mui_request,
            recipient=AgentId(type="MUISelectAgent", key="default"),
            cancellation_token=ctx.cancellation_token
        )
        
        # 显示选择的 MUI 组件
        mui_components_str = ', '.join(mui_response.selected_components) if mui_response.selected_components else '(无)'
        self.logger.debug(f"{indent}  MUI: [{mui_components_str}]")
        
        # 4. 通过消息传递请求 ComponentMigrateAgent 迁移组件
        migrate_request = ComponentMigrationRequest(
            wpf_source=xaml_code,
            dependencies_code=wpf_dependencies,
            child_react_code=child_react_code,
            mui_components_docs=mui_response.docs
        )
        
        # 发送消息到 ComponentMigrateAgent
        migrate_response = await self.send_message(
            message=migrate_request,
            recipient=AgentId(type="ComponentMigrateAgent", key="default"),
            cancellation_token=ctx.cancellation_token
        )
        
        # 显示迁移结果（输出完整描述，不截断）
        self.logger.debug(f"{indent}  => {migrate_response.component_name}: {migrate_response.description}")
        
        # 5. 构建结果
        result = {
            "node_path": node_path,
            "wpf_tag": wpf_tag,
            "component_name": migrate_response.component_name,
            "description": migrate_response.description,
            "react_code": migrate_response.react_code,
            "imports": migrate_response.imports,
            "interfaces": migrate_response.interfaces,
            "migration_notes": migrate_response.migration_notes,
            "selected_mui_components": mui_response.selected_components,
            "children": child_results
        }
        
        # 6. 缓存结果
        self.migration_cache[node_path] = result
        
        return result
    
    async def _assemble_page(
        self,
        page_name: str,
        page_source: str,
        root_result: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        页面整合阶段：将根组件整合成完整的 React 页面
        
        Args:
            page_name: 页面名称
            page_source: 完整的 WPF 页面源代码
            root_result: 根组件的迁移结果
            
        Returns:
            整合后的页面代码字典
        """
        system_prompt = """You are an expert in React and TypeScript.

## Version Requirements

- **MUI (Material-UI)**: Use version 7.3.7
- **AutoGen**: Use version 0.7.5
- Ensure all imports and API usage are compatible with these specific versions

Your task: Take a migrated React component and assemble it into a complete, properly formatted TypeScript page.

## What you must do:

1. Put ALL imports at the top (deduplicate if needed)
2. Put TypeScript interfaces after imports (if any)
3. Put the complete component code (with all its logic and TSX)
4. Put `export default ComponentName;` at the very end

## Example Output Structure:

```typescript
import React, { useState } from 'react';
import { Button, TextField } from '@mui/material';

interface MyProps {
  name: string;
}

const MyComponent: React.FC<MyProps> = ({ name }) => {
  return <div>{name}</div>;
};

export default MyComponent;
```

## Critical Rules:

- Output ONLY valid TypeScript/React code
- NO markdown code blocks (no ```)
- NO JSON formatting
- NO explanatory text or comments outside the code
- Preserve ALL component logic and TSX from the input
- Only organize structure (imports → interfaces → component → export)
- Ensure all MUI imports and API calls are compatible with MUI v7.3.7

Your response must be pure TypeScript code that can be directly saved to a .tsx file."""
        
        # 提取根组件信息
        component_name = root_result.get("component_name", page_name)
        component_code = root_result.get("react_code", "")
        imports = root_result.get("imports", [])
        interfaces = root_result.get("interfaces", "")
        
        
        # 构建用户提示
        imports_text = "\n".join(imports) if isinstance(imports, list) else str(imports)
        
        user_prompt = f"""Assemble this into a complete .tsx page file:

Component Name: {component_name}

Imports:
{imports_text}

Interfaces:
{interfaces}

Component Code:
{component_code}

---

Requirements:
1. Organize all imports at the top (deduplicate)
2. Add interfaces after imports
3. Include the full component code
4. Add "export default {component_name};" at the end
5. Ensure all MUI imports and API usage are compatible with MUI v7.3.7
6. If AutoGen is used, ensure compatibility with AutoGen v0.7.5

Output valid TypeScript code ready to save as {page_name}.tsx"""
        
        # 调用 LLM（注意：页面整合阶段必须使用纯文本模式，不能用 JSON 模式）
        from src.llm import LLMClient, LLMConfig
        temp_config = LLMConfig(
            model=self.llm_client.config.model,
            temperature=self.llm_client.config.temperature,
            json_mode=False  # 页面整合必须使用纯文本模式
        )
        temp_client = LLMClient(config=temp_config)
        
        page_code = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 清理可能的 markdown 代码块标记
        page_code = page_code.strip()
        
        # 移除开头的 markdown 代码块标记
        if page_code.startswith("```"):
            lines = page_code.split('\n')
            # 移除第一行（可能是 ```typescript, ```tsx, 或只是 ```）
            if lines[0].startswith("```"):
                lines = lines[1:]
            # 移除最后一行（如果是 ```）
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            page_code = '\n'.join(lines).strip()
        
        return {
            "page_code": page_code,
            "page_description": f"Complete React page for {page_name}",
            "assembly_notes": "Page assembled from root component with organized imports and proper exports"
        }
    
    def _load_control_json(self, control_json_path: str) -> Dict[str, Any]:
        """加载 control JSON 文件"""
        path = Path(control_json_path)
        
        if not path.exists():
            raise FileNotFoundError(f"control JSON 文件不存在: {control_json_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _merge_child_react_code(self, child_results: List[Dict[str, Any]]) -> str:
        """合并子组件的 React 代码"""
        if not child_results:
            return ""
        
        merged_code = []
        
        for child in child_results:
            component_name = child.get("component_name", "Unknown")
            react_code = child.get("react_code", "")
            
            merged_code.append(f"// Child Component: {component_name}")
            merged_code.append(react_code)
            merged_code.append("")
        
        return "\n".join(merged_code)
    
    def _format_typescript_code(self, code: str) -> str:
        """
        格式化 TypeScript 代码
        
        Args:
            code: 原始代码
            
        Returns:
            格式化后的代码
        """
        import re
        
        # 如果代码已经有合理的换行（多于5行），则认为已格式化，直接返回
        lines = code.split('\n')
        if len(lines) > 5:
            return code
        
        # 否则，对压缩的单行代码进行格式化
        # 在 { 后添加换行
        code = re.sub(r'\{\s*', '{\n', code)
        
        # 在 ; 后添加换行（但不包括 for 循环中的分号）
        code = re.sub(r';(?!\s*\))', ';\n', code)
        
        # 在 } 前后添加换行
        code = re.sub(r'\s*\}', '\n}', code)
        code = re.sub(r'\}(?!\s*[,;)\]])', '}\n', code)
        
        # 在 JSX 标签间添加换行
        code = re.sub(r'>(?=<[A-Z])', '>\n', code)  # 组件标签
        code = re.sub(r'>(?=<[a-z])', '>\n', code)  # HTML 标签
        
        # 在箭头函数的 => 后添加换行
        code = re.sub(r'=>\s*\{', '=> {\n', code)
        
        # 清理多余的空行
        code = re.sub(r'\n\s*\n\s*\n+', '\n\n', code)
        
        # 基本的缩进（简单实现）
        lines = code.split('\n')
        indented_lines = []
        indent_level = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                indented_lines.append('')
                continue
            
            # 减少缩进（在 } 行）
            if stripped.startswith('}') or stripped.startswith(']') or stripped.startswith(')'):
                indent_level = max(0, indent_level - 1)
            
            # 添加缩进
            indented_lines.append('  ' * indent_level + stripped)
            
            # 增加缩进（在 { 后）
            if stripped.endswith('{') or stripped.endswith('[') or stripped.endswith('('):
                indent_level += 1
            # 特殊情况：行包含 { 和 }，但 { 更多
            elif stripped.count('{') > stripped.count('}'):
                indent_level += stripped.count('{') - stripped.count('}')
            elif stripped.count('}') > stripped.count('{'):
                pass  # 已经在前面处理过了
        
        return '\n'.join(indented_lines)
    
    def _generate_complete_tsx_file(
        self,
        root_component: Dict[str, Any],
        output_path: Path
    ):
        """
        生成完整的 TSX 文件
        
        注意：页面整合后，react_code 已经是完整的页面代码，直接写入即可。
        
        Args:
            root_component: 根组件的迁移结果
            output_path: 输出文件路径
        """
        react_code = root_component.get("react_code", "")
        
        if not react_code:
            self.logger.warning("react_code 为空，无法生成文件")
            return
        
        # 直接写入完整的页面代码（已经过页面整合阶段处理）
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(react_code)
    
    def _generate_output(
        self,
        page_name: str,
        result: Dict[str, Any],
        output_dir: Optional[str] = None
    ) -> str:
        """
        生成输出文件
        
        Args:
            page_name: 页面名称
            result: 迁移结果
            output_dir: 输出目录（如果为 None 则使用默认目录）
        
        Returns:
            输出文件路径
        """
        # 确定输出目录
        if output_dir:
            out_dir = Path(output_dir)
        else:
            out_dir = self.migration_dir
        
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成 JSON 文件（完整的迁移结果）
        json_path = out_dir / f"{page_name}_migration.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"✓ 保存完整迁移结果: {json_path}")
        
        # 生成完整的 TSX 文件
        tsx_path = out_dir / f"{page_name}.tsx"
        root_component = result.get("root_component", {})
        
        if root_component:
            self._generate_complete_tsx_file(root_component, tsx_path)
            self.logger.info(f"✓ 保存 TypeScript 组件文件: {tsx_path}")
        else:
            self.logger.warning("未找到根组件数据，跳过 TSX 文件生成")
        
        return str(json_path)
