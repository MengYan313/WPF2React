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
from src.logger import get_logger
from .mui_select_agent import MUISelectAgent
from .component_migrate_agent import ComponentMigrateAgent
from .page_migrate_agent import PageMigrateAgent
from .page_assembly_agent import PageAssemblyAgent
from .resource_migrate_agent import ResourceMigrateAgent
from .cs_migrate_agent import CsMigrateAgent
from .data_migrate_agent import DataMigrateAgent
from .messages import (
    MUISelectionRequest,
    ComponentMigrationRequest,
    PageMigrationRequest,
    ResourceMigrationRequest,
    BatchCsMigrationRequest,
    DataMigrationRequest
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
        mui_select_llm_config: Optional[LLMConfig] = None,
        component_migrate_llm_config: Optional[LLMConfig] = None,
        cs_migrate_llm_config: Optional[LLMConfig] = None,
        data_migrate_llm_config: Optional[LLMConfig] = None,
        page_assembly_llm_config: Optional[LLMConfig] = None,
        page_migrate_llm_config: Optional[LLMConfig] = None,
        resource_migrate_llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化迁移团队
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
            mui_select_llm_config: MUI 选择 Agent 的 LLM 配置
            component_migrate_llm_config: 组件迁移 Agent 的 LLM 配置
            cs_migrate_llm_config: C# 迁移 Agent 的 LLM 配置
            data_migrate_llm_config: 数据迁移 Agent 的 LLM 配置
            page_assembly_llm_config: 页面整合 Agent 的 LLM 配置
            page_migrate_llm_config: 页面迁移 Agent 的 LLM 配置（用于布局分析）
            resource_migrate_llm_config: 资源迁移 Agent 的 LLM 配置（通常为 None）
        """
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        self.mui_select_llm_config = mui_select_llm_config
        self.component_migrate_llm_config = component_migrate_llm_config
        self.cs_migrate_llm_config = cs_migrate_llm_config
        self.data_migrate_llm_config = data_migrate_llm_config
        self.page_assembly_llm_config = page_assembly_llm_config
        self.page_migrate_llm_config = page_migrate_llm_config
        self.resource_migrate_llm_config = resource_migrate_llm_config
        
        # 向后兼容：保留旧的属性名
        self.select_llm_config = mui_select_llm_config
        self.migrate_llm_config = component_migrate_llm_config
        
        # 创建日志记录器（自动检测脚本名称）
        self.logger = get_logger(name="MigrationTeam")
        
        # Runtime 将在需要时创建
        self.runtime: Optional[SingleThreadedAgentRuntime] = None
        
        # Agent ID
        self.mui_select_id = AgentId(type="MUISelectAgent", key="default")
        self.component_migrate_id = AgentId(type="ComponentMigrateAgent", key="default")
        self.page_migrate_id = AgentId(type="PageMigrateAgent", key="default")
        self.resource_migrate_id = AgentId(type="ResourceMigrateAgent", key="default")
        self.cs_migrate_id = AgentId(type="CsMigrateAgent", key="default")
        self.data_migrate_id = AgentId(type="DataMigrateAgent", key="default")
        
        # 获取 LLM 模型名称（用于日志）
        mui_model = mui_select_llm_config.model if mui_select_llm_config else "gpt-4o (default)"
        component_model = component_migrate_llm_config.model if component_migrate_llm_config else "gpt-4o (default)"
        cs_model = cs_migrate_llm_config.model if cs_migrate_llm_config else "None"
        data_model = data_migrate_llm_config.model if data_migrate_llm_config else "None"
        page_assembly_model = page_assembly_llm_config.model if page_assembly_llm_config else "None"
        page_migrate_model = page_migrate_llm_config.model if page_migrate_llm_config else "None"
        
        self.logger.info("✓ 迁移团队初始化完成（使用 Autogen Runtime）")
        self.logger.debug(f"  - 项目: {project_name}")
        self.logger.debug(f"  - MUI 选择 Agent: {mui_model}")
        self.logger.debug(f"  - 组件迁移 Agent: {component_model}")
        self.logger.debug(f"  - C# 迁移 Agent: {cs_model}")
        self.logger.debug(f"  - 数据迁移 Agent: {data_model}")
        self.logger.debug(f"  - 页面整合 Agent: {page_assembly_model}")
        self.logger.debug(f"  - 页面迁移 Agent: {page_migrate_model}")
        self.logger.debug(f"  - 通信方式: 消息传递（Autogen 最佳实践）\n")
    
    async def _setup_runtime(self):
        """创建并配置 Runtime"""
        if self.runtime is not None:
            return
        
        self.runtime = SingleThreadedAgentRuntime()
        
        # 注册 Agent（使用官方 API）
        # 1. MUI 选择 Agent
        await MUISelectAgent.register(
            self.runtime,
            "MUISelectAgent",
            lambda: MUISelectAgent(
                llm_config=self.mui_select_llm_config,
                output_base_dir=str(self.output_base_dir)
            )
        )
        
        # 2. 组件迁移 Agent
        await ComponentMigrateAgent.register(
            self.runtime,
            "ComponentMigrateAgent",
            lambda: ComponentMigrateAgent(
                llm_config=self.component_migrate_llm_config,
                output_base_dir=str(self.output_base_dir)
            )
        )
        
        # 3. 页面迁移 Agent（用于布局分析）
        await PageMigrateAgent.register(
            self.runtime,
            "PageMigrateAgent",
            lambda: PageMigrateAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                llm_config=self.page_migrate_llm_config
            )
        )
        
        # 4. 页面整合 Agent
        await PageAssemblyAgent.register(
            self.runtime,
            "PageAssemblyAgent",
            lambda: PageAssemblyAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                llm_config=self.page_assembly_llm_config
            )
        )
        
        # 5. 资源迁移 Agent（不需要 LLM）
        await ResourceMigrateAgent.register(
            self.runtime,
            "ResourceMigrateAgent",
            lambda: ResourceMigrateAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                llm_config=self.resource_migrate_llm_config
            )
        )
        
        # 6. C# 迁移 Agent
        await CsMigrateAgent.register(
            self.runtime,
            "CsMigrateAgent",
            lambda: CsMigrateAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                llm_config=self.cs_migrate_llm_config
            )
        )
        
        # 7. 数据迁移 Agent
        await DataMigrateAgent.register(
            self.runtime,
            "DataMigrateAgent",
            lambda: DataMigrateAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                llm_config=self.data_migrate_llm_config
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
        # 创建页面迁移请求
        # 注意：页面迁移开始的日志由 PageMigrateAgent 输出，这里不再重复
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
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"✓ 页面 '{page_name}' 迁移完成")
            self.logger.debug(f"  - 总组件数: {response.total_components}")
            self.logger.debug(f"  - 已迁移组件: {response.migrated_components}")
            self.logger.debug(f"  - 输出路径: {response.output_path}")
            self.logger.info(f"{'='*80}\n")
        else:
            self.logger.error(f"\n{'='*80}")
            self.logger.error(f"✗ 页面 '{page_name}' 迁移失败")
            self.logger.error(f"  - 错误: {response.error}")
            self.logger.error(f"{'='*80}\n")
        
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
        child_react_code: str = "",
        template: str = "",
        data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        迁移单个组件（异步）
        
        Args:
            wpf_source: WPF 组件源代码
            wpf_tag: WPF 组件标签名（用于 MUI 选择）
            child_react_code: 子组件的 React 代码
            template: 依赖的模板代码（DataTemplate/ControlTemplate 等）
            data: 依赖的数据资源（从 data_resources.json 中提取）
            
        Returns:
            迁移结果字典
        """
        if data is None:
            data = {}
        self.logger.info(f"{'='*80}")
        self.logger.info(f"开始迁移组件: {wpf_tag or 'Unknown'}")
        self.logger.info(f"{'='*80}")
        
        # 设置 Runtime
        await self._setup_runtime()
        
        self.runtime.start()
        try:
            # 1. 使用 MUISelectAgent 选择 MUI 组件
            self.logger.debug("[1/2] 选择 MUI 组件...")
            
            mui_request = MUISelectionRequest(
                wpf_source=wpf_source,
                wpf_tag=wpf_tag,
                max_components=3
            )
            
            mui_response = await self.runtime.send_message(
                message=mui_request,
                recipient=self.mui_select_id
            )
            
            self.logger.debug(f"  选中: {', '.join(mui_response.selected_components)}")
            
            # 2. 构建 MUI 组件名和使用示例的配对列表
            mui_components_docs = []
            for component_name, usage_example in zip(mui_response.selected_components, mui_response.docs):
                mui_components_docs.append(f"[{component_name}]\n{usage_example}\n[/{component_name}]")
            mui_components_docs_str = "\n\n".join(mui_components_docs)
            
            # 3. 使用 ComponentMigrateAgent 迁移组件
            self.logger.debug("[2/2] 迁移组件...")
            
            migrate_request = ComponentMigrationRequest(
                wpf_source=wpf_source,
                child_react_code=child_react_code,
                mui_components_docs=mui_components_docs_str,
                template=template,
                data=data if data else {}
            )
            
            migrate_response = await self.runtime.send_message(
                message=migrate_request,
                recipient=self.component_migrate_id
            )
        finally:
            await self.runtime.stop_when_idle()
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"✓ 组件迁移完成: {migrate_response.component_name}")
        self.logger.debug(f"  - MUI 组件: {', '.join(mui_response.selected_components)}")
        self.logger.info(f"{'='*80}\n")
        
        # 返回结果字典
        return {
            "component_name": migrate_response.component_name,
            "imports": migrate_response.imports,
            "interfaces": migrate_response.interfaces,
            "react_code": migrate_response.react_code,
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
    
    async def migrate_resources(
        self,
        resource_dependency_file: str,
        resources_dir: str
    ) -> Dict[str, Any]:
        """
        迁移资源文件（异步）
        
        Args:
            resource_dependency_file: 资源依赖文件路径
            resources_dir: 资源输出目录
            
        Returns:
            资源迁移结果字典
        """
        request = ResourceMigrationRequest(
            project_name=self.project_name,
            resource_dependency_file=resource_dependency_file,
            resources_dir=resources_dir
        )
        
        # 设置 Runtime
        await self._setup_runtime()
        
        self.runtime.start()
        try:
            response = await self.runtime.send_message(
                message=request,
                recipient=self.resource_migrate_id
            )
        finally:
            await self.runtime.stop_when_idle()
        
        return {
            "success": response.success,
            "message": response.message,
            "resources_migrated": response.resources_migrated,
            "resources_failed": response.resources_failed,
            "migrated_files": response.migrated_files,
            "failed_files": response.failed_files,
            "resources_dir": response.resources_dir
        }
    
    async def migrate_cs_files(
        self,
        cs_dependency_file: str,
        output_dir: str,
        ts_info_file: str
    ) -> Dict[str, Any]:
        """
        批量迁移 C# 文件（异步）
        
        Args:
            cs_dependency_file: C# 依赖文件路径
            output_dir: C# 文件输出目录
            ts_info_file: ts_info.json 文件路径
            
        Returns:
            C# 文件迁移结果字典
        """
        request = BatchCsMigrationRequest(
            project_name=self.project_name,
            cs_dependency_file=cs_dependency_file,
            output_dir=output_dir,
            ts_info_file=ts_info_file
        )
        
        # 设置 Runtime
        await self._setup_runtime()
        
        self.runtime.start()
        try:
            response = await self.runtime.send_message(
                message=request,
                recipient=self.cs_migrate_id
            )
        finally:
            await self.runtime.stop_when_idle()
        
        return {
            "success": response.success,
            "message": response.message,
            "files_migrated": response.files_migrated,
            "files_failed": response.files_failed,
            "migrated_files": response.migrated_files,
            "failed_files": response.failed_files,
            "output_dir": response.output_dir
        }
    
    async def migrate_data(
        self,
        data_resources_file: str,
        output_file: str
    ) -> Dict[str, Any]:
        """
        迁移数据资源（异步）
        
        Args:
            data_resources_file: 数据资源文件路径
            output_file: 输出文件路径（result/{project_name}/data.ts）
            
        Returns:
            数据迁移结果字典
        """
        request = DataMigrationRequest(
            project_name=self.project_name,
            data_resources_file=data_resources_file,
            output_file=output_file
        )
        
        # 设置 Runtime
        await self._setup_runtime()
        
        self.runtime.start()
        try:
            response = await self.runtime.send_message(
                message=request,
                recipient=self.data_migrate_id
            )
        finally:
            await self.runtime.stop_when_idle()
        
        return {
            "success": response.success,
            "message": response.message,
            "data_resources_migrated": response.data_resources_migrated,
            "data_resources_failed": response.data_resources_failed,
            "migrated_keys": response.migrated_keys,
            "failed_keys": response.failed_keys,
            "output_file": response.output_file
        }
