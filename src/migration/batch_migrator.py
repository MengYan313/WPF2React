# -*- coding: utf-8 -*-
"""
批量页面迁移模块

负责读取页面依赖关系文件，按照迁移顺序批量迁移所有页面。
"""

import json
import shutil
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.logger import get_logger
from .migration_team import MigrationTeam
from src.llm import LLMConfig


class BatchMigrator:
    """
    批量页面迁移器
    
    职责：
    1. 读取 outputs/{project_name}/dependency/page_dependency.json
    2. 获取迁移顺序（migration_order）
    3. 按照顺序依次迁移每个页面
    4. 记录迁移进度和结果
    """
    
    def __init__(
        self,
        project_name: str,
        output_base_dir: str = "outputs",
        select_llm_config: Optional[LLMConfig] = None,
        migrate_llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化批量迁移器
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
            select_llm_config: MUI 选择 Agent 的 LLM 配置
            migrate_llm_config: 组件迁移 Agent 的 LLM 配置
        """
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        self.select_llm_config = select_llm_config
        self.migrate_llm_config = migrate_llm_config
        
        # 创建日志记录器
        self.logger = get_logger(name="BatchMigrator")
        
        # 依赖文件路径
        self.dependency_file = (
            self.output_base_dir / project_name / "dependency" / "page_dependency.json"
        )
        
        # 资源依赖文件路径
        self.resource_dependency_file = (
            self.output_base_dir / project_name / "dependency" / "resource_dependency.json"
        )
        
        # 结果目录（项目根目录下的 result/{project_name}）
        project_root = Path(__file__).parent.parent.parent
        self.result_dir = project_root / "result" / project_name
        
        # 资源目录（result/{project_name}/public，遵循 React 最佳实践）
        self.resources_dir = self.result_dir / "public"
        
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
            if page_name not in pages:
                self.logger.warning(
                    f"迁移顺序中包含未知页面: {page_name}，将跳过该页面"
                )
        
        self.logger.info(f"✓ 成功加载依赖关系文件: {self.dependency_file}")
        self.logger.debug(f"  - 总页面数: {dependency_graph.get('total_pages', 0)}")
        self.logger.debug(f"  - 迁移顺序: {' -> '.join(migration_order)}")
        
        return dependency_graph
    
    def migrate_resources(self) -> Dict[str, Any]:
        """
        迁移项目资源文件
        
        根据 resource_dependency.json 文件复制资源到 result/{project_name}/public/
        
        Returns:
            资源迁移结果字典
            
        Raises:
            FileNotFoundError: 如果资源依赖文件不存在
            ValueError: 如果资源依赖文件格式不正确
        """
        # 检查资源依赖文件是否存在
        if not self.resource_dependency_file.exists():
            self.logger.warning(
                f"资源依赖文件不存在: {self.resource_dependency_file}\n"
                f"跳过资源迁移。如需迁移资源，请先运行: python -m src.parser.resource_dependency"
            )
            return {
                'success': False,
                'message': '资源依赖文件不存在',
                'resources_migrated': 0,
                'resources_failed': 0
            }
        
        # 读取资源依赖文件
        try:
            with open(self.resource_dependency_file, 'r', encoding='utf-8') as f:
                resource_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"资源依赖文件格式错误: {self.resource_dependency_file}\n"
                f"JSON 解析错误: {e}"
            )
        
        # 验证必要字段
        if 'resources' not in resource_data:
            raise ValueError(
                f"资源依赖文件缺少 'resources' 字段: {self.resource_dependency_file}"
            )
        
        resources = resource_data.get('resources', [])
        if not resources:
            self.logger.info("未找到需要迁移的资源文件")
            return {
                'success': True,
                'message': '没有资源需要迁移',
                'resources_migrated': 0,
                'resources_failed': 0
            }
        
        # 创建资源目录
        self.resources_dir.mkdir(parents=True, exist_ok=True)
        
        # 记录迁移结果
        migrated_count = 0
        failed_count = 0
        migrated_files = []
        failed_files = []
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"开始迁移资源文件: {self.project_name}")
        self.logger.info(f"资源总数: {len(resources)}")
        self.logger.info(f"目标目录: {self.resources_dir}")
        self.logger.info(f"{'='*80}\n")
        
        # 复制每个资源文件
        for resource in resources:
            resource_path = resource.get('absolute_path')
            file_name = resource.get('file_name', '')
            exists = resource.get('exists', False)
            
            if not resource_path:
                self.logger.warning(f"  跳过资源（无绝对路径）: {file_name}")
                failed_count += 1
                failed_files.append(file_name)
                continue
            
            source_path = Path(resource_path)
            
            if not exists or not source_path.exists():
                self.logger.warning(f"  跳过资源（文件不存在）: {file_name} ({resource_path})")
                failed_count += 1
                failed_files.append(file_name)
                continue
            
            try:
                # 目标文件路径
                dest_path = self.resources_dir / file_name
                
                # 如果目标文件已存在，先删除
                if dest_path.exists():
                    dest_path.unlink()
                
                # 复制文件
                shutil.copy2(source_path, dest_path)
                migrated_count += 1
                migrated_files.append(file_name)
                self.logger.info(f"  ✓ 已复制: {file_name} -> {dest_path}")
                
            except Exception as e:
                self.logger.error(f"  ✗ 复制失败: {file_name} - {e}")
                failed_count += 1
                failed_files.append(file_name)
        
        # 输出总结
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"资源迁移完成: {self.project_name}")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"总资源数: {len(resources)}")
        self.logger.info(f"成功迁移: {migrated_count}")
        self.logger.info(f"迁移失败: {failed_count}")
        
        if migrated_files:
            self.logger.info(f"\n成功迁移的资源:")
            for file_name in migrated_files:
                self.logger.info(f"  ✓ {file_name}")
        
        if failed_files:
            self.logger.warning(f"\n迁移失败的资源:")
            for file_name in failed_files:
                self.logger.warning(f"  ✗ {file_name}")
        
        self.logger.info(f"{'='*80}\n")
        
        return {
            'success': True,
            'message': '资源迁移完成',
            'resources_migrated': migrated_count,
            'resources_failed': failed_count,
            'migrated_files': migrated_files,
            'failed_files': failed_files,
            'resources_dir': str(self.resources_dir)
        }
    
    async def migrate_all_pages(self) -> Dict[str, Any]:
        """
        按照迁移顺序批量迁移所有页面
        
        流程：
        1. 先迁移资源文件
        2. 再迁移页面
        
        Returns:
            包含所有迁移结果的字典
        """
        # 第一步：迁移资源文件
        self.logger.info("="*80)
        self.logger.info("第一步：迁移资源文件")
        self.logger.info("="*80)
        resource_result = self.migrate_resources()
        
        # 第二步：加载依赖关系图并迁移页面
        self.logger.info("="*80)
        self.logger.info("第二步：迁移页面")
        self.logger.info("="*80)
        
        # 加载依赖关系图
        dependency_graph = self.load_dependency_graph()
        
        # 获取迁移顺序
        migration_order = dependency_graph['migration_order']
        pages_info = dependency_graph.get('pages', {})
        
        # 初始化迁移团队
        if self.migration_team is None:
            self.migration_team = MigrationTeam(
                project_name=self.project_name,
                output_base_dir=str(self.output_base_dir),
                select_llm_config=self.select_llm_config,
                migrate_llm_config=self.migrate_llm_config
            )
        
        # 清空之前的结果
        self.migration_results.clear()
        
        # 记录开始
        total_pages = len(migration_order)
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"开始批量迁移项目: {self.project_name}")
        self.logger.info(f"总页面数: {total_pages}")
        self.logger.info(f"迁移顺序: {' -> '.join(migration_order)}")
        self.logger.info(f"{'='*80}\n")
        
        # 按顺序迁移每个页面
        successful_pages = []
        failed_pages = []
        
        for idx, page_name in enumerate(migration_order, 1):
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"进度: [{idx}/{total_pages}] 迁移页面: {page_name}")
            self.logger.info(f"{'='*80}\n")
            
            # 获取页面信息
            page_info = pages_info.get(page_name, {})
            dependencies = page_info.get('dependencies', [])
            
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
                result = await self.migration_team.migrate_page(page_name=page_name)
                
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
                    'page_name': page_name,
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
        
        # 生成总结报告
        summary = {
            'project_name': self.project_name,
            'total_pages': total_pages,
            'successful_pages': len(successful_pages),
            'failed_pages': len(failed_pages),
            'successful_page_names': successful_pages,
            'failed_page_names': failed_pages,
            'migration_order': migration_order,
            'results': self.migration_results,
            'resource_migration': resource_result  # 添加资源迁移结果
        }
        
        # 输出总结
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"批量迁移完成: {self.project_name}")
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
                     if r.get('page_name') == page),
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
                'message': '尚未执行批量迁移'
            }
        
        successful = [r for r in self.migration_results if r.get('success', False)]
        failed = [r for r in self.migration_results if not r.get('success', False)]
        
        return {
            'project_name': self.project_name,
            'status': 'completed',
            'total_pages': len(self.migration_results),
            'successful_pages': len(successful),
            'failed_pages': len(failed),
            'successful_page_names': [r['page_name'] for r in successful],
            'failed_page_names': [r['page_name'] for r in failed],
            'results': self.migration_results
        }


# python -m src.migration.batch_migrator
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    
    # 加载环境变量
    load_dotenv()
    
    async def main():
        """批量迁移 ExpenseItDemo 项目所有页面"""
        # 创建 LLM 配置（使用 gpt-4o-mini）
        # MUISelectAgent 需要 JSON 模式（返回 JSON 格式的选择结果）
        select_llm_config = LLMConfig(
            model="gpt-4o-mini",
            temperature=0,
            json_mode=True  # MUI 组件选择需要 JSON 模式
        )
        
        # ComponentMigrateAgent 需要 JSON 模式（返回 JSON 格式的迁移结果）
        migrate_llm_config = LLMConfig(
            model="gpt-4o-mini",
            temperature=0,
            json_mode=True  # 组件迁移需要 JSON 模式
        )
        
        # PageMigrateAgent 不需要 JSON 模式（页面整合阶段返回纯代码）
        # 注意：PageMigrateAgent 使用 migrate_llm_config，但会在内部设置为 json_mode=False
        
        # 创建批量迁移器
        migrator = BatchMigrator(
            project_name="ExpenseItDemo",
            output_base_dir="outputs",
            select_llm_config=select_llm_config,
            migrate_llm_config=migrate_llm_config
        )
        
        # 执行批量迁移
        summary = await migrator.migrate_all_pages()
        
        # 输出总结
        print("\n" + "="*80)
        print("批量迁移完成总结")
        print("="*80)
        print(f"项目名称: {summary['project_name']}")
        print(f"总页面数: {summary['total_pages']}")
        print(f"成功迁移: {summary['successful_pages']}")
        print(f"迁移失败: {summary['failed_pages']}")
        
        if summary['successful_page_names']:
            print(f"\n成功迁移的页面:")
            for page in summary['successful_page_names']:
                print(f"  ✓ {page}")
        
        if summary['failed_page_names']:
            print(f"\n迁移失败的页面:")
            for page in summary['failed_page_names']:
                result = next(
                    (r for r in summary['results'] if r.get('page_name') == page),
                    None
                )
                error = result.get('error', 'Unknown error') if result else 'Unknown error'
                print(f"  ✗ {page}: {error}")
        
        print("="*80)
        
        return summary
    
    # 运行异步主函数
    asyncio.run(main())

