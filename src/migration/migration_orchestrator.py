"""
迁移编排模块

负责编排整个迁移流程：
1. 迁移资源文件（通过 ResourceMigrateAgent）
2. 迁移 C# 文件（通过 CsMigrateAgent）
3. 迁移页面（通过 PageMigrateAgent）
"""

import json
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.common.logging import get_logger
from src.common.progress import progress
from src.common.source_identity import SOURCE_ID_SCHEME, normalize_page_id
from .migration_team import MigrationTeam
from src.llm import LLMConfig


class MigrationOrchestrator:
    """
    迁移编排器
    
    职责：
    1. 编排整个迁移流程（资源 -> C# -> 页面）
    2. 通过 MigrationTeam 调用各个 Agent 完成迁移任务
    3. 记录迁移进度和结果
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
        初始化迁移编排器
        
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
        
        # 创建日志记录器
        self.logger = get_logger(name="MigrationOrchestrator")
        
        # 依赖文件路径
        self.dependency_file = (
            self.output_base_dir / project_name / "dependency" / "page_dependency.json"
        )
        
        # 资源依赖文件路径
        self.resource_dependency_file = (
            self.output_base_dir / project_name / "dependency" / "resource_dependency.json"
        )
        
        # C# 依赖文件路径
        self.cs_dependency_file = (
            self.output_base_dir / project_name / "dependency" / "cs_dependency.json"
        )
        
        # 数据资源文件路径
        self.data_resources_file = (
            self.output_base_dir / project_name / "dependency" / "data_resources.json"
        )
        
        # 结果目录（项目根目录下的 results/{project_name}）
        self.result_dir = Path(result_dir) if result_dir else Path("results") / project_name
        
        # 资源目录（results/{project_name}/public，遵循 React 最佳实践）
        self.resources_dir = self.result_dir / "public"
        
        # C# 文件输出目录（results/{project_name}）
        self.cs_output_dir = self.result_dir
        
        # TypeScript 文件信息 JSON 文件路径（outputs/{project_name}/migration/ts_info.json）
        self.ts_info_file = (
            self.output_base_dir / project_name / "migration" / "ts_info.json"
        )
        
        # 迁移团队（延迟初始化）
        self.migration_team: Optional[MigrationTeam] = None
        
        # 迁移结果
        self.migration_results: List[Dict[str, Any]] = []
    
    def load_dependency_graph(self) -> Dict[str, Any]:
        """
        加载页面依赖关系图
        
        Returns:
            依赖关系图字典
            
        Raises:
            FileNotFoundError: 如果依赖文件不存在
            ValueError: 如果依赖文件格式不正确或缺少 migration_order
        """
        if not self.dependency_file.exists():
            raise FileNotFoundError(
                f"依赖文件不存在: {self.dependency_file}\n"
                f"请先运行页面依赖分析: python -m src.parser.page_dependency"
            )
        
        with open(self.dependency_file, 'r', encoding='utf-8') as f:
            dependency_graph = json.load(f)

        if dependency_graph.get('id_scheme') != SOURCE_ID_SCHEME:
            raise ValueError(
                f"页面依赖文件未使用 {SOURCE_ID_SCHEME}；请重新运行阶段 1 解析器"
            )
        
        # 验证必要字段
        if 'migration_order' not in dependency_graph:
            raise ValueError(
                f"依赖文件缺少 'migration_order' 字段: {self.dependency_file}\n"
                f"请重新运行页面依赖分析以生成迁移顺序。"
            )
        
        migration_order = dependency_graph['migration_order']
        if not migration_order or not isinstance(migration_order, list):
            raise ValueError(
                f"依赖文件中的 'migration_order' 字段无效: {self.dependency_file}\n"
                f"期望一个非空的页面名称列表。"
            )
        
        # 验证页面信息
        if 'pages' not in dependency_graph:
            raise ValueError(
                f"依赖文件缺少 'pages' 字段: {self.dependency_file}"
            )
        
        pages = dependency_graph['pages']
        for page_name in migration_order:
            normalize_page_id(page_name)
            if page_name not in pages:
                self.logger.warning(
                    f"迁移顺序中包含未知页面: {page_name}，将跳过该页面"
                )
                continue
            page_info = pages[page_name]
            if page_info.get("page_id") != page_name:
                raise ValueError(f"页面键 {page_name} 与 page_id 不一致")
            if not page_info.get("component_name"):
                raise ValueError(f"页面 {page_name} 缺少路径派生的 component_name")
        
        self.logger.info(f"✓ 成功加载依赖关系文件: {self.dependency_file}")
        self.logger.debug(f"  - 总页面数: {dependency_graph.get('total_pages', 0)}")
        self.logger.debug(f"  - 迁移顺序: {' -> '.join(migration_order)}")
        
        return dependency_graph
    
    async def migrate_resources(self) -> Dict[str, Any]:
        """
        迁移项目资源文件（通过 ResourceMigrateAgent）
        
        Returns:
            资源迁移结果字典
        """
        # 初始化迁移团队（如果尚未初始化）
        if self.migration_team is None:
            self.migration_team = MigrationTeam(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                result_dir=str(self.result_dir),
                enable_mui_retrieval=self.enable_mui_retrieval,
                mui_select_llm_config=self.mui_select_llm_config,
                component_migrate_llm_config=self.component_migrate_llm_config,
                cs_migrate_llm_config=self.cs_migrate_llm_config,
                data_migrate_llm_config=self.data_migrate_llm_config,
                page_assembly_llm_config=self.page_assembly_llm_config,
                page_migrate_llm_config=self.page_migrate_llm_config,
                resource_migrate_llm_config=self.resource_migrate_llm_config
            )
        
        # 通过 MigrationTeam 调用 ResourceMigrateAgent
        return await self.migration_team.migrate_resources(
            resource_dependency_file=str(self.resource_dependency_file),
            resources_dir=str(self.resources_dir)
        )
    
    async def migrate_cs_files(self) -> Dict[str, Any]:
        """
        迁移项目 C# 文件（通过 CsMigrateAgent）
        
        Returns:
            C# 文件迁移结果字典
        """
        # 初始化迁移团队（如果尚未初始化）
        if self.migration_team is None:
            self.migration_team = MigrationTeam(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                result_dir=str(self.result_dir),
                enable_mui_retrieval=self.enable_mui_retrieval,
                mui_select_llm_config=self.mui_select_llm_config,
                component_migrate_llm_config=self.component_migrate_llm_config,
                cs_migrate_llm_config=self.cs_migrate_llm_config,
                data_migrate_llm_config=self.data_migrate_llm_config,
                page_assembly_llm_config=self.page_assembly_llm_config,
                page_migrate_llm_config=self.page_migrate_llm_config,
                resource_migrate_llm_config=self.resource_migrate_llm_config
            )
        
        # 通过 MigrationTeam 调用 CsMigrateAgent
        return await self.migration_team.migrate_cs_files(
            cs_dependency_file=str(self.cs_dependency_file),
            output_dir=str(self.cs_output_dir),
            ts_info_file=str(self.ts_info_file)
        )
    
    async def migrate_data(self) -> Dict[str, Any]:
        """
        迁移项目数据资源（通过 DataMigrateAgent）
        
        Returns:
            数据迁移结果字典
        """
        # 初始化迁移团队（如果尚未初始化）
        if self.migration_team is None:
            self.migration_team = MigrationTeam(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                result_dir=str(self.result_dir),
                enable_mui_retrieval=self.enable_mui_retrieval,
                mui_select_llm_config=self.mui_select_llm_config,
                component_migrate_llm_config=self.component_migrate_llm_config,
                cs_migrate_llm_config=self.cs_migrate_llm_config,
                data_migrate_llm_config=self.data_migrate_llm_config,
                page_assembly_llm_config=self.page_assembly_llm_config,
                page_migrate_llm_config=self.page_migrate_llm_config,
                resource_migrate_llm_config=self.resource_migrate_llm_config
            )
        
        # 数据输出文件路径（results/{project_name}/data.ts）
        data_output_file = self.result_dir / "data.ts"
        
        # 通过 MigrationTeam 调用 DataMigrateAgent
        return await self.migration_team.migrate_data(
            data_resources_file=str(self.data_resources_file),
            output_file=str(data_output_file)
        )
    
    async def orchestrate_migration(
        self,
        page_names: Optional[List[str]] = None,
        *,
        run_project_stages: bool = True,
    ) -> Dict[str, Any]:
        """
        编排整个迁移流程
        
        流程：
        1. 先迁移资源文件
        2. 再迁移 C# 文件
        3. 最后迁移页面
        
        Returns:
            包含所有迁移结果的字典
        """
        stage_progress = progress(
            total=4,
            desc=f"迁移 {self.project_name}",
            unit="阶段",
        )
        if run_project_stages:
            # 第一步：迁移资源文件
            self.logger.info("="*80)
            self.logger.info("第一步：迁移资源文件")
            self.logger.info("="*80)
            resource_result = await self.migrate_resources()
            stage_progress.update(1)

            # 第二步：迁移 C# 文件
            self.logger.info("="*80)
            self.logger.info("第二步：迁移 C# 文件")
            self.logger.info("="*80)
            cs_result = await self.migrate_cs_files()
            stage_progress.update(1)

            # 第三步：迁移数据资源
            self.logger.info("="*80)
            self.logger.info("第三步：迁移数据资源")
            self.logger.info("="*80)
            data_result = await self.migrate_data()
            stage_progress.update(1)
        else:
            resource_result = {"success": True, "status": "skipped_for_smoke"}
            cs_result = {"success": True, "status": "skipped_for_smoke"}
            data_result = {"success": True, "status": "skipped_for_smoke"}
            stage_progress.update(3)
        
        # 第四步：加载依赖关系图并迁移页面
        self.logger.info("="*80)
        self.logger.info("第四步：迁移页面")
        self.logger.info("="*80)
        
        # 加载依赖关系图
        dependency_graph = self.load_dependency_graph()
        
        # 获取迁移顺序
        migration_order = list(dependency_graph['migration_order'])
        if page_names is not None:
            requested_pages = list(dict.fromkeys(page_names))
            unknown_pages = [
                page_name
                for page_name in requested_pages
                if page_name not in dependency_graph.get('pages', {})
            ]
            if unknown_pages:
                raise ValueError(
                    f"指定页面不在依赖图中: {', '.join(unknown_pages)}"
                )
            requested_set = set(requested_pages)
            migration_order = [
                page_name for page_name in migration_order if page_name in requested_set
            ]
            if not migration_order:
                raise ValueError("page_names 过滤后没有可迁移页面")
        pages_info = dependency_graph.get('pages', {})
        
        # 初始化迁移团队
        if self.migration_team is None:
            self.migration_team = MigrationTeam(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                result_dir=str(self.result_dir),
                enable_mui_retrieval=self.enable_mui_retrieval,
                mui_select_llm_config=self.mui_select_llm_config,
                component_migrate_llm_config=self.component_migrate_llm_config,
                cs_migrate_llm_config=self.cs_migrate_llm_config,
                data_migrate_llm_config=self.data_migrate_llm_config,
                page_assembly_llm_config=self.page_assembly_llm_config,
                page_migrate_llm_config=self.page_migrate_llm_config,
                resource_migrate_llm_config=self.resource_migrate_llm_config
            )
        
        # 清空之前的结果
        self.migration_results.clear()
        
        # 记录开始
        total_pages = len(migration_order)
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"开始编排迁移项目: {self.project_name}")
        self.logger.info(f"总页面数: {total_pages}")
        self.logger.info(f"迁移顺序: {' -> '.join(migration_order)}")
        self.logger.info(f"{'='*80}\n")
        
        # 按顺序迁移每个页面
        successful_pages = []
        failed_pages = []
        
        page_progress = progress(
            migration_order,
            desc=f"迁移页面：{self.project_name}",
            unit="页面",
            leave=False,
        )
        for idx, page_name in enumerate(page_progress, 1):
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"进度: [{idx}/{total_pages}] 迁移页面: {page_name}")
            self.logger.info(f"{'='*80}\n")
            
            # 获取页面信息
            page_info = pages_info.get(page_name, {})
            dependencies = page_info.get('dependencies', [])
            control_file = page_info.get('control_file')
            if not control_file:
                raise ValueError(f"页面 {page_name} 缺少 control_file")
            project_output_dir = self.output_base_dir / self.project_name
            resolved_control_file = (project_output_dir / control_file).resolve()
            try:
                resolved_control_file.relative_to(project_output_dir.resolve())
            except ValueError as exc:
                raise ValueError(
                    f"页面 {page_name} 的 control_file 越出项目输出目录"
                ) from exc
            
            if dependencies:
                self.logger.debug(f"  依赖页面: {', '.join(dependencies)}")
                # 验证依赖页面是否已成功迁移
                for dep in dependencies:
                    if dep not in successful_pages:
                        self.logger.warning(
                            f"  警告: 依赖页面 '{dep}' 尚未成功迁移，"
                            f"但将继续迁移 '{page_name}'"
                        )
            
            try:
                # 迁移页面
                result = await self.migration_team.migrate_page(
                    page_id=page_name,
                    component_name=page_info['component_name'],
                    control_json_path=str(resolved_control_file),
                )
                
                # 记录结果
                result['index'] = idx
                result['dependencies'] = dependencies
                self.migration_results.append(result)
                
                if result.get('success', False):
                    successful_pages.append(page_name)
                    self.logger.info(
                        f"✓ [{idx}/{total_pages}] 页面 '{page_name}' 迁移成功"
                    )
                else:
                    failed_pages.append(page_name)
                    self.logger.error(
                        f"✗ [{idx}/{total_pages}] 页面 '{page_name}' 迁移失败: {result.get('error', 'Unknown error')}"
                    )
                    
            except Exception as e:
                # 记录异常
                error_result = {
                    'index': idx,
                    'page_id': page_name,
                    'dependencies': dependencies,
                    'success': False,
                    'error': str(e),
                    'total_components': 0,
                    'migrated_components': 0,
                    'output_path': ''
                }
                self.migration_results.append(error_result)
                failed_pages.append(page_name)
                self.logger.error(
                    f"✗ [{idx}/{total_pages}] 页面 '{page_name}' 迁移异常: {e}",
                    exc_info=True
                )

        stage_progress.update(1)
        stage_progress.close()
        
        # 生成总结报告
        summary = {
            'project_name': self.project_name,
            'total_pages': total_pages,
            'successful_pages': len(successful_pages),
            'failed_pages': len(failed_pages),
            'successful_page_ids': successful_pages,
            'failed_page_ids': failed_pages,
            'migration_order': migration_order,
            'results': self.migration_results,
            'resource_migration': resource_result,  # 添加资源迁移结果
            'cs_migration': cs_result,  # 添加 C# 文件迁移结果
            'data_migration': data_result  # 添加数据迁移结果
        }
        
        # 输出总结
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"迁移编排完成: {self.project_name}")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"总页面数: {total_pages}")
        self.logger.info(f"成功: {len(successful_pages)}")
        self.logger.info(f"失败: {len(failed_pages)}")
        
        if successful_pages:
            self.logger.info(f"\n成功迁移的页面:")
            for page in successful_pages:
                self.logger.info(f"  ✓ {page}")
        
        if failed_pages:
            self.logger.error(f"\n迁移失败的页面:")
            for page in failed_pages:
                error_msg = next(
                    (r.get('error', 'Unknown error') 
                     for r in self.migration_results 
                     if r.get('page_id') == page),
                    'Unknown error'
                )
                self.logger.error(f"  ✗ {page}: {error_msg}")
        
        self.logger.info(f"{'='*80}\n")
        
        return summary
    
    def get_migration_summary(self) -> Dict[str, Any]:
        """
        获取迁移总结（如果已执行迁移）
        
        Returns:
            迁移总结字典
        """
        if not self.migration_results:
            return {
                'project_name': self.project_name,
                'status': 'not_started',
                'message': '尚未执行迁移编排'
            }
        
        successful = [r for r in self.migration_results if r.get('success', False)]
        failed = [r for r in self.migration_results if not r.get('success', False)]
        
        return {
            'project_name': self.project_name,
            'status': 'completed',
            'total_pages': len(self.migration_results),
            'successful_pages': len(successful),
            'failed_pages': len(failed),
            'successful_page_ids': [r['page_id'] for r in successful],
            'failed_page_ids': [r['page_id'] for r in failed],
            'results': self.migration_results
        }


if __name__ == "__main__":
    import sys
    import asyncio
    from dotenv import load_dotenv
    
    # 加载环境变量
    load_dotenv()
    
    if len(sys.argv) < 2:
        logger = get_logger("MigrationOrchestrator")
        logger.error("用法: python -m src.migration.migration_orchestrator <project_name>")
        logger.error("示例: python -m src.migration.migration_orchestrator ExpenseItDemo")
        sys.exit(1)
    
    project_name = sys.argv[1]
    
    async def test_migration():
        """测试迁移的前两个阶段：资源迁移和 C# 文件迁移"""
        logger = get_logger("MigrationOrchestrator")
        
        logger.info("=" * 70)
        logger.info(f"测试迁移编排器: {project_name}")
        logger.info("=" * 70)
        
        # 创建 LLM 配置（统一约定：temperature=0、JSON mode）
        low_llm_config = LLMConfig.json_mode_config()
        
        # 创建迁移编排器
        orchestrator = MigrationOrchestrator(
            project_name=project_name,
            output_base_dir="outputs",
            mui_select_llm_config=low_llm_config,
            component_migrate_llm_config=low_llm_config,
            cs_migrate_llm_config=low_llm_config,
            data_migrate_llm_config=low_llm_config,
            page_assembly_llm_config=low_llm_config,
            page_migrate_llm_config=low_llm_config,
            resource_migrate_llm_config=None
        )
        
        try:
            # 第一阶段：测试资源迁移
            logger.info("\n" + "=" * 70)
            logger.info("第一阶段：测试资源迁移")
            logger.info("=" * 70)
            resource_result = await orchestrator.migrate_resources()
            
            logger.info("\n资源迁移结果:")
            logger.info(f"  成功: {resource_result.get('success', False)}")
            logger.info(f"  消息: {resource_result.get('message', '')}")
            logger.info(f"  成功迁移: {resource_result.get('resources_migrated', 0)}")
            logger.info(f"  迁移失败: {resource_result.get('resources_failed', 0)}")
            
            if resource_result.get('migrated_files'):
                logger.info(f"  成功迁移的文件: {', '.join(resource_result.get('migrated_files', []))}")
            if resource_result.get('failed_files'):
                logger.warning(f"  失败的文件: {', '.join(resource_result.get('failed_files', []))}")
            
            # 第二阶段：测试 C# 文件迁移
            logger.info("\n" + "=" * 70)
            logger.info("第二阶段：测试 C# 文件迁移")
            logger.info("=" * 70)
            cs_result = await orchestrator.migrate_cs_files()
            
            logger.info("\nC# 文件迁移结果:")
            logger.info(f"  成功: {cs_result.get('success', False)}")
            logger.info(f"  消息: {cs_result.get('message', '')}")
            logger.info(f"  成功迁移: {cs_result.get('files_migrated', 0)}")
            logger.info(f"  迁移失败: {cs_result.get('files_failed', 0)}")
            
            if cs_result.get('migrated_files'):
                logger.info(f"  成功迁移的文件: {', '.join(cs_result.get('migrated_files', []))}")
            if cs_result.get('failed_files'):
                logger.warning(f"  失败的文件: {', '.join(cs_result.get('failed_files', []))}")
            
            logger.info("\n" + "=" * 70)
            logger.info("✅ 前两个阶段测试完成")
            logger.info("=" * 70)
            
        except Exception as e:
            logger.error(f"\n✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    # 运行异步测试函数
    asyncio.run(test_migration())
