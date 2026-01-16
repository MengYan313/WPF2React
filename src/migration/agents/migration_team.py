# -*- coding: utf-8 -*-
"""
Migration Team

使用 Autogen Runtime 管理多 Agent 系统，通过消息传递实现 Agent 间通信。
遵循 Autogen 最佳实践。
"""

from typing import Optional, Dict, Any
from pathlib import Path

from autogen_core import SingleThreadedAgentRuntime, AgentId

from src.llm import LLMConfig
from .mui_select_agent import MUISelectAgent
from .component_migrate_agent import ComponentMigrateAgent
from .page_migrate_agent import PageMigrateAgent
from .messages import (
    MUISelectionRequest,
    ComponentMigrationRequest,
    PageMigrationRequest
)


class MigrationTeam:
    """
    迁移团队
    
    使用 Autogen Runtime 管理 Agent 生命周期和消息路由。
    遵循 Autogen 最佳实践：Agent 通过消息传递通信，而不是直接调用。
    """
    
    def __init__(
        self,
        project_name: str,
        output_base_dir: str = "outputs",
        select_llm_config: Optional[LLMConfig] = None,
        migrate_llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化迁移团队
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
            select_llm_config: MUI 选择 Agent 的 LLM 配置（默认 gpt-4o）
            migrate_llm_config: 组件迁移 Agent 的 LLM 配置（默认 gpt-4o）
        """
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        self.select_llm_config = select_llm_config
        self.migrate_llm_config = migrate_llm_config
        
        # Runtime 将在需要时创建
        self.runtime: Optional[SingleThreadedAgentRuntime] = None
        
        # Agent ID
        self.mui_select_id = AgentId(type="MUISelectAgent", key="default")
        self.component_migrate_id = AgentId(type="ComponentMigrateAgent", key="default")
        self.page_migrate_id = AgentId(type="PageMigrateAgent", key="default")
        
        # 获取 LLM 模型名称
        select_model = select_llm_config.model if select_llm_config else "gpt-4o (default)"
        migrate_model = migrate_llm_config.model if migrate_llm_config else "gpt-4o (default)"
        
        print(f"✓ 迁移团队初始化完成（使用 Autogen Runtime）")
        print(f"  - 项目: {project_name}")
        print(f"  - MUI 选择 Agent: {select_model}")
        print(f"  - 组件迁移 Agent: {migrate_model}")
        print(f"  - 通信方式: 消息传递（Autogen 最佳实践）")
        print()
    
    async def _setup_runtime(self):
        """创建并配置 Runtime"""
        if self.runtime is not None:
            return
        
        self.runtime = SingleThreadedAgentRuntime()
        
        # 注册 Agent（使用官方 API）
        await MUISelectAgent.register(
            self.runtime,
            "MUISelectAgent",
            lambda: MUISelectAgent(llm_config=self.select_llm_config)
        )
        
        await ComponentMigrateAgent.register(
            self.runtime,
            "ComponentMigrateAgent",
            lambda: ComponentMigrateAgent(llm_config=self.migrate_llm_config)
        )
        
        await PageMigrateAgent.register(
            self.runtime,
            "PageMigrateAgent",
            lambda: PageMigrateAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir)
            )
        )
    
    async def migrate_page(
        self,
        page_name: str,
        control_json_path: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        迁移单个页面（异步）
        
        Args:
            page_name: 页面名称（例如 "MainWindow"）
            control_json_path: control JSON 文件路径（如果为 None 则自动推导）
            output_dir: 输出目录（如果为 None 则使用默认目录）
            
        Returns:
            迁移结果字典
        """
        print(f"="*80)
        print(f"开始迁移页面: {page_name}")
        print(f"="*80)
        
        # 创建页面迁移请求
        request = PageMigrationRequest(
            control_json_path=control_json_path,
            page_name=page_name,
            output_dir=output_dir
        )
        
        # 设置 Runtime
        await self._setup_runtime()
        
        # 启动 Runtime 并发送消息
        self.runtime.start()
        try:
            # 发送消息到 PageMigrateAgent
            response = await self.runtime.send_message(
                message=request,
                recipient=self.page_migrate_id
            )
        finally:
            await self.runtime.stop_when_idle()
        
        if response.success:
            print(f"\n" + "="*80)
            print(f"✓ 页面 '{page_name}' 迁移完成")
            print(f"  - 总组件数: {response.total_components}")
            print(f"  - 已迁移组件: {response.migrated_components}")
            print(f"  - 输出路径: {response.output_path}")
            print(f"="*80)
        else:
            print(f"\n" + "="*80)
            print(f"✗ 页面 '{page_name}' 迁移失败")
            print(f"  - 错误: {response.error}")
            print(f"="*80)
        
        # 返回结果字典
        return {
            "page_name": response.page_name,
            "total_components": response.total_components,
            "migrated_components": response.migrated_components,
            "output_path": response.output_path,
            "success": response.success,
            "error": response.error
        }
    
    async def migrate_component(
        self,
        wpf_source: str,
        wpf_tag: str = "",
        dependencies_code: str = "",
        child_react_code: str = ""
    ) -> Dict[str, Any]:
        """
        迁移单个组件（异步）
        
        Args:
            wpf_source: WPF 组件源代码
            wpf_tag: WPF 组件标签名（用于 MUI 选择）
            dependencies_code: 依赖代码（如 ViewModel）
            child_react_code: 子组件的 React 代码
            
        Returns:
            迁移结果字典
        """
        print(f"="*80)
        print(f"开始迁移组件: {wpf_tag or 'Unknown'}")
        print(f"="*80)
        
        # 设置 Runtime
        await self._setup_runtime()
        
        self.runtime.start()
        try:
            # 1. 使用 MUISelectAgent 选择 MUI 组件
            print(f"\n[1/2] 选择 MUI 组件...")
            
            mui_request = MUISelectionRequest(
                wpf_source=wpf_source,
                wpf_tag=wpf_tag,
                max_components=3
            )
            
            mui_response = await self.runtime.send_message(
                message=mui_request,
                recipient=self.mui_select_id
            )
            
            print(f"  选中: {', '.join(mui_response.selected_components)}")
            print(f"  理由: {mui_response.reasoning}")
            
            # 2. 使用 ComponentMigrateAgent 迁移组件
            print(f"\n[2/2] 迁移组件...")
            
            migrate_request = ComponentMigrationRequest(
                wpf_source=wpf_source,
                dependencies_code=dependencies_code,
                child_react_code=child_react_code,
                mui_components_docs=mui_response.docs
            )
            
            migrate_response = await self.runtime.send_message(
                message=migrate_request,
                recipient=self.component_migrate_id
            )
        finally:
            await self.runtime.stop_when_idle()
        
        print(f"\n" + "="*80)
        print(f"✓ 组件迁移完成: {migrate_response.component_name}")
        print(f"  - 描述: {migrate_response.description}")
        print(f"  - MUI 组件: {', '.join(mui_response.selected_components)}")
        print(f"="*80)
        
        # 返回结果字典
        return {
            "component_name": migrate_response.component_name,
            "description": migrate_response.description,
            "imports": migrate_response.imports,
            "interfaces": migrate_response.interfaces,
            "react_code": migrate_response.react_code,
            "migration_notes": migrate_response.migration_notes,
            "selected_mui_components": mui_response.selected_components,
            "mui_reasoning": mui_response.reasoning
        }
    
    async def select_mui_components(
        self,
        wpf_source: str,
        wpf_tag: str = "",
        max_components: int = 3
    ) -> Dict[str, Any]:
        """
        仅选择 MUI 组件（不执行迁移）
        
        Args:
            wpf_source: WPF 组件源代码
            wpf_tag: WPF 组件标签名
            max_components: 最多选择的组件数量
            
        Returns:
            选择结果字典
        """
        request = MUISelectionRequest(
            wpf_source=wpf_source,
            wpf_tag=wpf_tag,
            max_components=max_components
        )
        
        # 设置 Runtime
        await self._setup_runtime()
        
        self.runtime.start()
        try:
            response = await self.runtime.send_message(
                message=request,
                recipient=self.mui_select_id
            )
        finally:
            await self.runtime.stop_when_idle()
        
        return {
            "selected_components": response.selected_components,
            "reasoning": response.reasoning,
            "docs": response.docs
        }
