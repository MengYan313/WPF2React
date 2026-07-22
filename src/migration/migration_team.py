"""
Migration Team

使用 Autogen Runtime 管理多 Agent 系统，通过消息传递实现 Agent 间通信。
遵循 Autogen 最佳实践。
"""

from typing import Optional, Dict, Any
from pathlib import Path

from autogen_core import SingleThreadedAgentRuntime

from src.agents.base import default_agent_id, register_agent
from src.llm import LLMConfig
from src.common.logging import get_logger
from .mui_select_agent import MUISelectAgent
from .base import BaseMigrationAgent
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
        result_dir: Optional[str] = None,
        enable_mui_retrieval: bool = True,
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
            result_dir: 最终产物目录；默认 results/{project_name}
            enable_mui_retrieval: 是否启用 MUI 知识库检索与文档注入
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
        self.result_dir = Path(result_dir) if result_dir else Path("results") / project_name
        self.enable_mui_retrieval = enable_mui_retrieval
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
        self._active_runtime_agents: list[BaseMigrationAgent] = []
        self._llm_usage = {
            "logical_calls": 0,
            "provider_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        
        # Agent 标识
        self.mui_select_id = default_agent_id("MUISelectAgent")
        self.component_migrate_id = default_agent_id("ComponentMigrateAgent")
        self.page_migrate_id = default_agent_id("PageMigrateAgent")
        self.resource_migrate_id = default_agent_id("ResourceMigrateAgent")
        self.cs_migrate_id = default_agent_id("CsMigrateAgent")
        self.data_migrate_id = default_agent_id("DataMigrateAgent")
        
        # 获取 LLM 模型名称（用于日志）
        default_model = LLMConfig.model_for_tier("low")
        mui_model = mui_select_llm_config.model if mui_select_llm_config else default_model
        component_model = component_migrate_llm_config.model if component_migrate_llm_config else default_model
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
        self._active_runtime_agents = []
        
        # 注册 Agent（使用官方 API）
        # 1. MUI 选择 Agent
        await register_agent(
            self.runtime,
            "MUISelectAgent",
            lambda: self._track_runtime_agent(MUISelectAgent(
                llm_config=self.mui_select_llm_config,
                output_base_dir=str(self.output_base_dir),
                retrieval_enabled=self.enable_mui_retrieval,
            ))
        )

        # 2. 组件迁移 Agent
        await register_agent(
            self.runtime,
            "ComponentMigrateAgent",
            lambda: self._track_runtime_agent(ComponentMigrateAgent(
                llm_config=self.component_migrate_llm_config,
                output_base_dir=str(self.output_base_dir)
            ))
        )
        
        # 3. 页面迁移 Agent（用于布局分析）
        await register_agent(
            self.runtime,
            "PageMigrateAgent",
            lambda: self._track_runtime_agent(PageMigrateAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                result_dir=str(self.result_dir),
                llm_config=self.page_migrate_llm_config
            ))
        )
        
        # 4. 页面整合 Agent
        await register_agent(
            self.runtime,
            "PageAssemblyAgent",
            lambda: self._track_runtime_agent(PageAssemblyAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                result_dir=str(self.result_dir),
                llm_config=self.page_assembly_llm_config
            ))
        )
        
        # 5. 资源迁移 Agent（不需要 LLM）
        await register_agent(
            self.runtime,
            "ResourceMigrateAgent",
            lambda: self._track_runtime_agent(ResourceMigrateAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                llm_config=self.resource_migrate_llm_config
            ))
        )
        
        # 6. C# 迁移 Agent
        await register_agent(
            self.runtime,
            "CsMigrateAgent",
            lambda: self._track_runtime_agent(CsMigrateAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                llm_config=self.cs_migrate_llm_config
            ))
        )
        
        # 7. 数据迁移 Agent
        await register_agent(
            self.runtime,
            "DataMigrateAgent",
            lambda: self._track_runtime_agent(DataMigrateAgent(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                llm_config=self.data_migrate_llm_config
            ))
        )

    def _track_runtime_agent(
        self,
        agent: BaseMigrationAgent,
    ) -> BaseMigrationAgent:
        self._active_runtime_agents.append(agent)
        return agent

    def _capture_runtime_usage(self) -> None:
        for agent in self._active_runtime_agents:
            snapshot = agent.llm_usage_snapshot()
            for field in self._llm_usage:
                self._llm_usage[field] += snapshot[field]
        self._active_runtime_agents = []

    def get_llm_usage(self) -> Dict[str, int]:
        """返回当前 MigrationTeam 生命周期内累计的实际调用与 token。"""
        return dict(self._llm_usage)

    async def _send_message(self, message, recipient):
        """发送一条顶层请求，并释放完整的 Runtime 对象图。"""
        await self._setup_runtime()
        runtime = self.runtime
        runtime.start()
        try:
            return await runtime.send_message(
                message=message,
                recipient=recipient,
            )
        finally:
            try:
                await runtime.stop_when_idle()
            finally:
                self._capture_runtime_usage()
                await runtime.close()
                self.runtime = None
    
    async def migrate_page(
        self,
        page_id: str,
        component_name: str,
        control_json_path: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        迁移单个页面（异步）
        
        Args:
            page_id: 对应 XAML 的仓库相对路径
            component_name: TypeScript 组件符号
            control_json_path: control JSON 文件路径（如果为 None 则自动推导）
            output_dir: 输出目录（如果为 None 则使用默认目录）
            
        Returns:
            迁移结果字典
        """
        # 创建页面迁移请求
        # 注意：页面迁移开始的日志由 PageMigrateAgent 输出，这里不再重复
        request = PageMigrationRequest(
            control_json_path=control_json_path,
            page_id=page_id,
            component_name=component_name,
            output_dir=output_dir
        )
        
        response = await self._send_message(request, self.page_migrate_id)
        
        if response.success:
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"✓ 页面 '{page_id}' 迁移完成")
            self.logger.debug(f"  - 总组件数: {response.total_components}")
            self.logger.debug(f"  - 已迁移组件: {response.migrated_components}")
            self.logger.debug(f"  - 输出路径: {response.output_path}")
            self.logger.info(f"{'='*80}\n")
        else:
            self.logger.error(f"\n{'='*80}")
            self.logger.error(f"✗ 页面 '{page_id}' 迁移失败")
            self.logger.error(f"  - 错误: {response.error}")
            self.logger.error(f"{'='*80}\n")
        
        # 返回结果字典
        return {
            "page_id": response.page_id,
            "component_name": response.component_name,
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
            runtime = self.runtime
            try:
                await runtime.stop_when_idle()
            finally:
                self._capture_runtime_usage()
                await runtime.close()
                self.runtime = None
        
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
            "mui_reasoning": ""
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
        
        response = await self._send_message(request, self.mui_select_id)
        
        return {
            "selected_components": response.selected_components,
            "reasoning": "",
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
        
        response = await self._send_message(request, self.resource_migrate_id)
        
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
        
        response = await self._send_message(request, self.cs_migrate_id)
        
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
            output_file: 输出文件路径（results/{project_name}/data.ts）
            
        Returns:
            数据迁移结果字典
        """
        request = DataMigrationRequest(
            project_name=self.project_name,
            data_resources_file=data_resources_file,
            output_file=output_file
        )
        
        response = await self._send_message(request, self.data_migrate_id)
        
        return {
            "success": response.success,
            "message": response.message,
            "data_resources_migrated": response.data_resources_migrated,
            "data_resources_failed": response.data_resources_failed,
            "migrated_keys": response.migrated_keys,
            "failed_keys": response.failed_keys,
            "output_file": response.output_file
        }
