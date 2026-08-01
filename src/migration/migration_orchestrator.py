"""按依赖顺序编排完整的 WPF 到 React 迁移。"""

import json
from pathlib import Path
from typing import Any

from src.common.logging import get_logger
from src.common.progress import progress
from src.common.source_identity import normalize_page_id
from .migration_team import MigrationTeam
from src.llm import LLMConfig


class MigrationOrchestrator:
    """依次迁移资源、C#、数据和页面。"""
    
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
        self.logger = get_logger(name="MigrationOrchestrator")

        dependency_dir = self.output_base_dir / project_name / "dependency"
        self.dependency_file = dependency_dir / "page_dependency.json"
        self.resource_dependency_file = dependency_dir / "resource_dependency.json"
        self.cs_dependency_file = dependency_dir / "cs_dependency.json"
        self.data_resources_file = dependency_dir / "data_resources.json"
        self.resources_dir = self.result_dir / "public"
        self.cs_output_dir = self.result_dir
        self.ts_info_file = (
            self.output_base_dir / project_name / "migration" / "ts_info.json"
        )

        self.migration_team = MigrationTeam(
            project_name=project_name,
            output_base_dir=output_base_dir,
            result_dir=str(self.result_dir),
            enable_mui_retrieval=enable_mui_retrieval,
            llm_config=llm_config,
        )
        self.migration_results: list[dict[str, Any]] = []
    
    def load_dependency_graph(self) -> dict[str, Any]:
        """加载并校验页面依赖图的核心契约。"""
        if not self.dependency_file.exists():
            raise FileNotFoundError(
                f"依赖文件不存在: {self.dependency_file}\n"
                f"请先运行页面依赖分析: python -m src.parser.page_dependency"
            )

        dependency_graph = json.loads(
            self.dependency_file.read_text(encoding="utf-8")
        )

        migration_order = dependency_graph.get("migration_order")
        if not isinstance(migration_order, list) or not migration_order:
            raise ValueError(
                f"依赖文件中的 'migration_order' 字段无效: {self.dependency_file}\n"
                f"期望一个非空的页面名称列表。"
            )

        pages = dependency_graph.get("pages")
        if not isinstance(pages, dict):
            raise ValueError(
                f"依赖文件中的 'pages' 字段无效: {self.dependency_file}"
            )

        for page_name in migration_order:
            normalize_page_id(page_name)
            if page_name not in pages:
                raise ValueError(
                    f"迁移顺序中的页面不在 pages 中: {page_name}"
                )
            page_info = pages[page_name]
            if page_info.get("page_id") != page_name:
                raise ValueError(f"页面键 {page_name} 与 page_id 不一致")
            if not page_info.get("component_name"):
                raise ValueError(f"页面 {page_name} 缺少路径派生的 component_name")
        
        self.logger.info(f"✓ 成功加载依赖关系文件: {self.dependency_file}")
        self.logger.debug(f"  - 总页面数: {dependency_graph.get('total_pages', 0)}")
        self.logger.debug(f"  - 迁移顺序: {' -> '.join(migration_order)}")
        
        return dependency_graph
    
    async def migrate_resources(self) -> dict[str, Any]:
        """迁移项目静态资源。"""
        return await self.migration_team.migrate_resources(
            resource_dependency_file=str(self.resource_dependency_file),
            resources_dir=str(self.resources_dir)
        )

    async def migrate_cs_files(self) -> dict[str, Any]:
        """迁移项目 C# 文件。"""
        return await self.migration_team.migrate_cs_files(
            cs_dependency_file=str(self.cs_dependency_file),
            output_dir=str(self.cs_output_dir),
            ts_info_file=str(self.ts_info_file)
        )

    async def migrate_data(self) -> dict[str, Any]:
        """迁移项目数据资源。"""
        return await self.migration_team.migrate_data(
            data_resources_file=str(self.data_resources_file),
            output_file=str(self.result_dir / "data.ts")
        )

    def _select_pages(
        self,
        dependency_graph: dict[str, Any],
        page_names: list[str] | None,
    ) -> list[str]:
        migration_order = list(dependency_graph["migration_order"])
        if page_names is None:
            return migration_order

        requested_pages = list(dict.fromkeys(page_names))
        unknown_pages = [
            page_id
            for page_id in requested_pages
            if page_id not in dependency_graph["pages"]
        ]
        if unknown_pages:
            raise ValueError(f"指定页面不在依赖图中: {', '.join(unknown_pages)}")

        requested = set(requested_pages)
        selected = [page_id for page_id in migration_order if page_id in requested]
        if not selected:
            raise ValueError("page_names 过滤后没有可迁移页面")
        return selected

    def _resolve_control_file(
        self,
        page_id: str,
        page_info: dict[str, Any],
    ) -> Path:
        control_file = page_info.get("control_file")
        if not control_file:
            raise ValueError(f"页面 {page_id} 缺少 control_file")

        project_output_dir = (self.output_base_dir / self.project_name).resolve()
        resolved = (project_output_dir / control_file).resolve()
        try:
            resolved.relative_to(project_output_dir)
        except ValueError as exc:
            raise ValueError(
                f"页面 {page_id} 的 control_file 越出项目输出目录"
            ) from exc
        return resolved

    async def _migrate_page(
        self,
        index: int,
        total: int,
        page_id: str,
        page_info: dict[str, Any],
        successful_pages: list[str],
    ) -> dict[str, Any]:
        dependencies = page_info.get("dependencies", [])
        unresolved = [page for page in dependencies if page not in successful_pages]
        if unresolved:
            self.logger.warning(
                "页面 %s 的依赖尚未成功迁移，继续当前页面: %s",
                page_id,
                ", ".join(unresolved),
            )

        control_file = self._resolve_control_file(page_id, page_info)
        try:
            result = await self.migration_team.migrate_page(
                page_id=page_id,
                component_name=page_info["component_name"],
                control_json_path=str(control_file),
            )
        except Exception as exc:
            # 页面是批量迁移的隔离边界；单页失败不应丢弃后续页面。
            self.logger.error(
                "✗ [%d/%d] 页面 '%s' 迁移异常: %s",
                index,
                total,
                page_id,
                exc,
                exc_info=True,
            )
            result = {
                "page_id": page_id,
                "component_name": page_info["component_name"],
                "success": False,
                "error": str(exc),
                "total_components": 0,
                "migrated_components": 0,
                "output_path": "",
            }

        result.update(index=index, dependencies=dependencies)
        self.migration_results.append(result)
        if result["success"]:
            self.logger.info("✓ [%d/%d] 页面 '%s' 迁移成功", index, total, page_id)
        return result

    async def orchestrate_migration(
        self,
        page_names: list[str] | None = None,
        *,
        run_project_stages: bool = True,
    ) -> dict[str, Any]:
        """依次执行项目级迁移阶段，再按依赖顺序迁移页面。"""
        stage_progress = progress(
            total=4,
            desc=f"迁移 {self.project_name}",
            unit="阶段",
        )
        try:
            if run_project_stages:
                project_results = []
                stages = (
                    ("第一步：迁移资源文件", self.migrate_resources),
                    ("第二步：迁移 C# 文件", self.migrate_cs_files),
                    ("第三步：迁移数据资源", self.migrate_data),
                )
                for label, run_stage in stages:
                    self.logger.info("%s\n%s\n%s", "=" * 80, label, "=" * 80)
                    project_results.append(await run_stage())
                    stage_progress.update(1)
            else:
                skipped = {"success": True, "status": "skipped_for_smoke"}
                project_results = [skipped.copy() for _ in range(3)]
                stage_progress.update(3)

            self.logger.info(
                "%s\n第四步：迁移页面\n%s",
                "=" * 80,
                "=" * 80,
            )
            dependency_graph = self.load_dependency_graph()
            migration_order = self._select_pages(dependency_graph, page_names)
            pages_info = dependency_graph["pages"]
            self.migration_results.clear()

            total_pages = len(migration_order)
            self.logger.info(
                "开始编排迁移项目: %s；页面数: %d；顺序: %s",
                self.project_name,
                total_pages,
                " -> ".join(migration_order),
            )

            successful_pages: list[str] = []
            failed_pages: list[str] = []
            page_progress = progress(
                migration_order,
                desc=f"迁移页面：{self.project_name}",
                unit="页面",
                leave=False,
            )
            for index, page_id in enumerate(page_progress, 1):
                result = await self._migrate_page(
                    index,
                    total_pages,
                    page_id,
                    pages_info[page_id],
                    successful_pages,
                )
                target = successful_pages if result["success"] else failed_pages
                target.append(page_id)
            stage_progress.update(1)
        finally:
            stage_progress.close()

        resource_result, cs_result, data_result = project_results
        summary = {
            "project_name": self.project_name,
            "total_pages": total_pages,
            "successful_pages": len(successful_pages),
            "failed_pages": len(failed_pages),
            "successful_page_ids": successful_pages,
            "failed_page_ids": failed_pages,
            "migration_order": migration_order,
            "results": self.migration_results,
            "resource_migration": resource_result,
            "cs_migration": cs_result,
            "data_migration": data_result,
        }
        self.logger.info(
            "迁移编排完成: %s；成功: %d；失败: %d",
            self.project_name,
            len(successful_pages),
            len(failed_pages),
        )
        return summary
    
    def get_migration_summary(self) -> dict[str, Any]:
        """返回最近一次页面迁移的汇总。"""
        if not self.migration_results:
            return {
                "project_name": self.project_name,
                "status": "not_started",
                "message": "尚未执行迁移编排",
            }
        
        successful = [result for result in self.migration_results if result["success"]]
        failed = [result for result in self.migration_results if not result["success"]]
        
        return {
            "project_name": self.project_name,
            "status": "completed",
            "total_pages": len(self.migration_results),
            "successful_pages": len(successful),
            "failed_pages": len(failed),
            "successful_page_ids": [result["page_id"] for result in successful],
            "failed_page_ids": [result["page_id"] for result in failed],
            "results": self.migration_results,
        }
