# -*- coding: utf-8 -*-
"""
迁移模块统一入口

使用方式：
    命令行：
        python -m src.migration <project_name>
    
    编程方式：
        from src.migration import migrate_project
        results = await migrate_project("ExpenseItDemo")
        
        或
        
        from src.migration.__main__ import migrate_project
        results = await migrate_project("ExpenseItDemo")
"""

import sys
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

from src.logger import get_logger
from src.llm import LLMConfig
from .migration_orchestrator import MigrationOrchestrator


async def migrate_project(
    project_name: str,
    output_base_dir: str = "outputs"
) -> Dict[str, Any]:
    """
    迁移整个项目：执行批量迁移
    
    流程：
    1. 迁移资源文件
    2. 迁移 C# 文件
    3. 迁移数据资源
    4. 按照迁移顺序批量迁移所有页面
    
    Args:
        project_name: 项目名称（例如 "ExpenseItDemo"）
        output_base_dir: 输出基础目录（默认为 "outputs"）
    
    Returns:
        包含所有迁移结果的字典
    """
    # 初始化日志
    logger = get_logger("migration")
    
    logger.info("=" * 70)
    logger.info(f"开始迁移项目: {project_name}")
    logger.info("=" * 70)
    
    # ========== 按照模型名称配置 LLM ==========
    # 注意：所有 Agent 都不使用 JSON 模式，而是使用标记格式（如 [Component Name]...[/Component Name]）
    # 默认全部使用 gpt-4o-mini，可根据需要修改各个 Agent 使用的模型
    
    # 创建四个模型配置（统一约定：temperature=0、标记格式，见 LLMConfig.marker_mode）
    llm_config_gpt_4o_mini = LLMConfig.marker_mode("gpt-4o-mini")
    llm_config_gpt_4o = LLMConfig.marker_mode("gpt-4o")
    llm_config_gpt_5 = LLMConfig.marker_mode("gpt-5")
    llm_config_gpt_5_mini = LLMConfig.marker_mode("gpt-5-mini")
    
    # 创建迁移编排器
    orchestrator = MigrationOrchestrator(
        project_name=project_name,
        output_base_dir=output_base_dir,
        mui_select_llm_config=llm_config_gpt_4o_mini,
        component_migrate_llm_config=llm_config_gpt_4o_mini,
        cs_migrate_llm_config=llm_config_gpt_4o_mini,
        data_migrate_llm_config=llm_config_gpt_4o,
        page_assembly_llm_config=llm_config_gpt_4o,
        page_migrate_llm_config=llm_config_gpt_4o,
        resource_migrate_llm_config=None  # 资源迁移 Agent 不需要 LLM
    )
    
    # 执行迁移编排
    summary = await orchestrator.orchestrate_migration()
    
    logger.info("=" * 70)
    logger.info("✅ 项目迁移完成")
    logger.info("=" * 70)
    
    # 打印摘要
    logger.info("\n迁移摘要:")
    logger.info(f"  项目名称: {summary['project_name']}")
    logger.info(f"  总页面数: {summary['total_pages']}")
    logger.info(f"  成功迁移: {summary['successful_pages']}")
    logger.info(f"  迁移失败: {summary['failed_pages']}")
    
    if summary['successful_page_names']:
        logger.info(f"\n成功迁移的页面:")
        for page in summary['successful_page_names']:
            logger.info(f"  ✓ {page}")
    
    if summary['failed_page_names']:
        logger.error(f"\n迁移失败的页面:")
        for page in summary['failed_page_names']:
            result = next(
                (r for r in summary['results'] if r.get('page_name') == page),
                None
            )
            error = result.get('error', 'Unknown error') if result else 'Unknown error'
            logger.error(f"  ✗ {page}: {error}")
    
    # 资源迁移结果
    resource_result = summary.get('resource_migration', {})
    if resource_result.get('success'):
        logger.info(f"\n资源迁移:")
        logger.info(f"  成功迁移: {resource_result.get('resources_migrated', 0)}")
        logger.info(f"  迁移失败: {resource_result.get('resources_failed', 0)}")
    
    # C# 文件迁移结果
    cs_result = summary.get('cs_migration', {})
    if cs_result.get('success'):
        logger.info(f"\nC# 文件迁移:")
        logger.info(f"  成功迁移: {cs_result.get('files_migrated', 0)}")
        logger.info(f"  迁移失败: {cs_result.get('files_failed', 0)}")
    
    # 数据迁移结果
    data_result = summary.get('data_migration', {})
    if data_result.get('success'):
        logger.info(f"\n数据资源迁移:")
        logger.info(f"  成功迁移: {data_result.get('data_resources_migrated', 0)}")
        logger.info(f"  迁移失败: {data_result.get('data_resources_failed', 0)}")
        logger.info(f"  输出文件: {data_result.get('output_file', '')}")
    
    logger.info("=" * 70)
    
    return summary


# python -m src.migration ExpenseItDemo
# nohup python -m src.migration ExpenseItDemo &
if __name__ == "__main__":
    from dotenv import load_dotenv
    
    # 加载环境变量
    load_dotenv()
    
    if len(sys.argv) < 2:
        logger = get_logger("migration")
        logger.error("用法: python -m src.migration <project_name>")
        logger.error("示例: python -m src.migration ExpenseItDemo")
        sys.exit(1)
    
    project_name = sys.argv[1]
    
    async def main():
        """异步主函数"""
        try:
            summary = await migrate_project(project_name)
            
            # 检查是否有失败的页面
            if summary['failed_pages'] > 0:
                sys.exit(1)
            
        except Exception as e:
            logger = get_logger("migration")
            logger.error(f"\n✗ 迁移失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    # 运行异步主函数
    asyncio.run(main())

