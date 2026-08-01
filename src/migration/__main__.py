"""迁移模块统一入口。"""

import sys
import asyncio
from typing import Any

from src.common.logging import get_logger
from src.llm import LLMConfig
from .experiment_page_set import load_project_page_selection
from .migration_orchestrator import MigrationOrchestrator


async def migrate_project(
    project_name: str,
    output_base_dir: str = "outputs",
    page_names: list[str] | None = None,
) -> dict[str, Any]:
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
    
    # ========== 配置当前统一使用的低档 LLM ==========
    # 所有结构化响应统一使用 JSON mode。
    # 模型名称来自 OPENAI_MODEL_LOW；中、高档仅保留在环境配置中供未来切换。
    low_llm_config = LLMConfig.json_mode_config()
    
    # 创建迁移编排器
    orchestrator = MigrationOrchestrator(
        project_name=project_name,
        output_base_dir=output_base_dir,
        llm_config=low_llm_config,
    )
    
    # 执行迁移编排
    summary = await orchestrator.orchestrate_migration(page_names=page_names)
    
    logger.info("=" * 70)
    logger.info("✅ 项目迁移完成")
    logger.info("=" * 70)
    
    # 打印摘要
    logger.info("\n迁移摘要:")
    logger.info(f"  项目名称: {summary['project_name']}")
    logger.info(f"  总页面数: {summary['total_pages']}")
    logger.info(f"  成功迁移: {summary['successful_pages']}")
    logger.info(f"  迁移失败: {summary['failed_pages']}")
    
    if summary['successful_page_ids']:
        logger.info(f"\n成功迁移的页面:")
        for page in summary['successful_page_ids']:
            logger.info(f"  ✓ {page}")
    
    if summary['failed_page_ids']:
        logger.error(f"\n迁移失败的页面:")
        for page in summary['failed_page_ids']:
            result = next(
                (r for r in summary['results'] if r.get('page_id') == page),
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


def main() -> int:
    """命令行入口。"""
    import argparse
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description="将已解析的 WPF 项目迁移为 React")
    parser.add_argument("project_name", help="repos/ 与 outputs/ 下的项目目录名")
    parser.add_argument(
        "--output-base-dir",
        default="outputs",
        help="解析产物基础目录（默认: outputs）",
    )
    parser.add_argument(
        "--page",
        dest="page_names",
        action="append",
        help="只迁移指定 page ID；可重复传入",
    )
    parser.add_argument(
        "--page-set",
        help="从冻结实验页面集合读取当前项目 page ID",
    )
    args = parser.parse_args()
    load_dotenv()

    if args.page_names and args.page_set:
        parser.error("--page 与 --page-set 不能同时使用")
    page_names = args.page_names
    if args.page_set:
        page_names = list(
            load_project_page_selection(args.page_set, args.project_name).page_ids
        )

    async def run() -> bool:
        try:
            summary = await migrate_project(
                args.project_name,
                output_base_dir=args.output_base_dir,
                page_names=page_names,
            )
            return summary['failed_pages'] == 0
        except Exception as e:
            logger = get_logger("migration")
            logger.error(f"\n✗ 迁移失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    return 0 if asyncio.run(run()) else 1


if __name__ == "__main__":
    sys.exit(main())
