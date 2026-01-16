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

from .base import BaseMigrationAgent
from .messages import (
    PageMigrationRequest, 
    PageMigrationResponse,
    MUISelectionRequest,
    MUISelectionResponse,
    ComponentMigrationRequest,
    ComponentMigrationResponse
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
        output_base_dir: str = "outputs"
    ):
        """
        初始化页面迁移 Agent
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
        """
        # 初始化基类（页面迁移 Agent 本身不使用 LLM，而是协调其他 Agent）
        super().__init__(
            agent_type="PageMigrateAgent",
            llm_config=None
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
        
        if not tree:
            raise ValueError(f"control JSON 中没有 controls 结构: {control_json_path}")
        
        # 3. 递归迁移整个组件树
        root_result = await self._migrate_node_recursive(
            node=tree,
            node_path="root",
            wpf_dependencies="",
            ctx=ctx
        )
        
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
        
        # 生成 JSON 文件
        json_path = out_dir / f"{page_name}_migration.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 生成 TSX 文件（可选，提取根组件代码）
        tsx_path = out_dir / f"{page_name}.tsx"
        root_component = result.get("root_component", {})
        react_code = root_component.get("react_code", "")
        
        if react_code:
            with open(tsx_path, 'w', encoding='utf-8') as f:
                f.write(react_code)
        
        return str(json_path)
