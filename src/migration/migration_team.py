"""通过 AutoGen Runtime 编排迁移 Agent。"""

from pathlib import Path
from typing import Any

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
    """管理迁移 Agent 的注册、消息路由和 Runtime 生命周期。"""
    
    def __init__(
        self,
        project_name: str,
        output_base_dir: str = "outputs",
        result_dir: str | None = None,
        enable_mui_retrieval: bool = True,
        llm_config: LLMConfig | None = None,
    ) -> None:
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        self.result_dir = Path(result_dir) if result_dir else Path("results") / project_name
        self.enable_mui_retrieval = enable_mui_retrieval
        self.llm_config = llm_config or LLMConfig.json_mode_config()

        self.logger = get_logger(name="MigrationTeam")
        self.runtime: SingleThreadedAgentRuntime | None = None
        self._active_runtime_agents: list[BaseMigrationAgent] = []
        self._llm_usage = {
            "logical_calls": 0,
            "provider_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        self.mui_select_id = default_agent_id("MUISelectAgent")
        self.component_migrate_id = default_agent_id("ComponentMigrateAgent")
        self.page_migrate_id = default_agent_id("PageMigrateAgent")
        self.resource_migrate_id = default_agent_id("ResourceMigrateAgent")
        self.cs_migrate_id = default_agent_id("CsMigrateAgent")
        self.data_migrate_id = default_agent_id("DataMigrateAgent")

        self.logger.info("迁移团队初始化完成: %s", project_name)

    async def _setup_runtime(self) -> SingleThreadedAgentRuntime:
        """按需创建 Runtime 并注册全部 Agent。"""
        if self.runtime is not None:
            return self.runtime

        runtime = SingleThreadedAgentRuntime()
        self.runtime = runtime
        self._active_runtime_agents = []

        await register_agent(
            runtime,
            "MUISelectAgent",
            lambda: self._track_runtime_agent(
                MUISelectAgent(
                    llm_config=self.llm_config,
                    output_base_dir=str(self.output_base_dir),
                    retrieval_enabled=self.enable_mui_retrieval,
                )
            ),
        )

        await register_agent(
            runtime,
            "ComponentMigrateAgent",
            lambda: self._track_runtime_agent(
                ComponentMigrateAgent(
                    llm_config=self.llm_config,
                    output_base_dir=str(self.output_base_dir),
                )
            ),
        )

        await register_agent(
            runtime,
            "PageMigrateAgent",
            lambda: self._track_runtime_agent(
                PageMigrateAgent(
                    project_name=self.project_name,
                    output_base_dir=str(self.output_base_dir),
                    result_dir=str(self.result_dir),
                    llm_config=self.llm_config,
                )
            ),
        )

        await register_agent(
            runtime,
            "PageAssemblyAgent",
            lambda: self._track_runtime_agent(
                PageAssemblyAgent(
                    project_name=self.project_name,
                    output_base_dir=str(self.output_base_dir),
                    result_dir=str(self.result_dir),
                    llm_config=self.llm_config,
                )
            ),
        )

        await register_agent(
            runtime,
            "ResourceMigrateAgent",
            lambda: self._track_runtime_agent(
                ResourceMigrateAgent(
                    project_name=self.project_name,
                    output_base_dir=str(self.output_base_dir),
                )
            ),
        )

        await register_agent(
            runtime,
            "CsMigrateAgent",
            lambda: self._track_runtime_agent(
                CsMigrateAgent(
                    project_name=self.project_name,
                    output_base_dir=str(self.output_base_dir),
                    llm_config=self.llm_config,
                )
            ),
        )

        await register_agent(
            runtime,
            "DataMigrateAgent",
            lambda: self._track_runtime_agent(
                DataMigrateAgent(
                    project_name=self.project_name,
                    output_base_dir=str(self.output_base_dir),
                    llm_config=self.llm_config,
                )
            ),
        )
        return runtime

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

    def get_llm_usage(self) -> dict[str, int]:
        """返回当前 MigrationTeam 生命周期内累计的实际调用与 token。"""
        return dict(self._llm_usage)

    async def _close_runtime(self, runtime: SingleThreadedAgentRuntime) -> None:
        """停止 Runtime、汇总用量并释放模型客户端。"""
        try:
            await runtime.stop_when_idle()
        finally:
            self._capture_runtime_usage()
            await runtime.close()
            self.runtime = None

    async def _send_message(self, message, recipient):
        """发送一条顶层请求，并释放完整的 Runtime 对象图。"""
        runtime = await self._setup_runtime()
        runtime.start()
        try:
            return await runtime.send_message(
                message=message,
                recipient=recipient,
            )
        finally:
            await self._close_runtime(runtime)
    
    async def migrate_page(
        self,
        page_id: str,
        component_name: str,
        control_json_path: str | None = None,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        """迁移单个页面。"""
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

        return response.model_dump()
    
    async def migrate_component(
        self,
        wpf_source: str,
        wpf_tag: str = "",
        child_react_code: str = "",
        template: str = "",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """先选择 MUI 组件，再迁移单个 WPF 组件。"""
        self.logger.info(f"{'='*80}")
        self.logger.info(f"开始迁移组件: {wpf_tag or 'Unknown'}")
        self.logger.info(f"{'='*80}")

        runtime = await self._setup_runtime()
        runtime.start()
        try:
            self.logger.debug("[1/2] 选择 MUI 组件...")
            mui_request = MUISelectionRequest(
                wpf_source=wpf_source,
                wpf_tag=wpf_tag,
                max_components=3,
            )
            mui_response = await runtime.send_message(
                message=mui_request,
                recipient=self.mui_select_id,
            )
            self.logger.debug(f"  选中: {', '.join(mui_response.selected_components)}")

            mui_components_docs = "\n\n".join(
                f"### {component_name}\n{usage_example}"
                for component_name, usage_example in zip(
                    mui_response.selected_components,
                    mui_response.docs,
                )
            )

            self.logger.debug("[2/2] 迁移组件...")
            migrate_request = ComponentMigrationRequest(
                wpf_source=wpf_source,
                child_react_code=child_react_code,
                mui_components_docs=mui_components_docs,
                template=template,
                data=data or {},
            )
            migrate_response = await runtime.send_message(
                message=migrate_request,
                recipient=self.component_migrate_id,
            )
        finally:
            await self._close_runtime(runtime)
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"✓ 组件迁移完成: {migrate_response.component_name}")
        self.logger.debug(f"  - MUI 组件: {', '.join(mui_response.selected_components)}")
        self.logger.info(f"{'='*80}\n")
        
        return {
            "component_name": migrate_response.component_name,
            "imports": migrate_response.imports,
            "interfaces": migrate_response.interfaces,
            "react_code": migrate_response.react_code,
            "selected_mui_components": mui_response.selected_components,
        }
    
    async def select_mui_components(
        self,
        wpf_source: str,
        wpf_tag: str = "",
        max_components: int = 3,
    ) -> dict[str, Any]:
        """仅选择 MUI 组件。"""
        request = MUISelectionRequest(
            wpf_source=wpf_source,
            wpf_tag=wpf_tag,
            max_components=max_components,
        )
        response = await self._send_message(request, self.mui_select_id)
        return response.model_dump()
    
    async def migrate_resources(
        self,
        resource_dependency_file: str,
        resources_dir: str,
    ) -> dict[str, Any]:
        """迁移静态资源文件。"""
        request = ResourceMigrationRequest(
            project_name=self.project_name,
            resource_dependency_file=resource_dependency_file,
            resources_dir=resources_dir,
        )
        response = await self._send_message(request, self.resource_migrate_id)
        return response.model_dump()
    
    async def migrate_cs_files(
        self,
        cs_dependency_file: str,
        output_dir: str,
        ts_info_file: str,
    ) -> dict[str, Any]:
        """按依赖顺序迁移 C# 文件。"""
        request = BatchCsMigrationRequest(
            project_name=self.project_name,
            cs_dependency_file=cs_dependency_file,
            output_dir=output_dir,
            ts_info_file=ts_info_file,
        )
        response = await self._send_message(request, self.cs_migrate_id)
        return response.model_dump()
    
    async def migrate_data(
        self,
        data_resources_file: str,
        output_file: str,
    ) -> dict[str, Any]:
        """迁移数据资源并生成 data.ts。"""
        request = DataMigrationRequest(
            project_name=self.project_name,
            data_resources_file=data_resources_file,
            output_file=output_file,
        )
        response = await self._send_message(request, self.data_migrate_id)
        return response.model_dump()
