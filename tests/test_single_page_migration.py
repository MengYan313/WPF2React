# -*- coding: utf-8 -*-
"""
测试单个页面的迁移

使用方式：
    python -m tests.test_single_page_migration
    或
    python tests/test_single_page_migration.py (从项目根目录运行)
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from src.logger import get_logger
from src.llm import LLMConfig
from src.migration import MigrationTeam


async def test_create_expense_report_dialog_box():
    """
    测试 CreateExpenseReportDialogBox 页面的迁移
    """
    # 加载环境变量
    load_dotenv()
    
    # 初始化日志
    logger = get_logger("test_single_page_migration")
    
    # 项目名称
    project_name = "ExpenseItDemo"
    page_name = "CreateExpenseReportDialogBox"
    
    # Control JSON 文件路径
    control_json_path = f"outputs/{project_name}/dependency/control_{page_name}.json"
    
    logger.info("=" * 80)
    logger.info(f"测试单个页面迁移: {page_name}")
    logger.info("=" * 80)
    logger.info(f"项目名称: {project_name}")
    logger.info(f"Control JSON 路径: {control_json_path}")
    logger.info("=" * 80)
    
    # 检查 Control JSON 文件是否存在
    control_json_file = Path(control_json_path)
    if not control_json_file.exists():
        logger.error(f"✗ Control JSON 文件不存在: {control_json_path}")
        logger.error("请先运行解析步骤:")
        logger.error("  python -m src.parser ExpenseItDemo")
        return False
    
    logger.info(f"✓ Control JSON 文件存在: {control_json_path}")
    
    # 创建 LLM 配置
    # 使用 gpt-4o-mini 进行测试（可以根据需要修改）
    select_llm_config = LLMConfig(
        model="gpt-4o-mini",
        temperature=0,
        json_mode=True  # MUI 组件选择需要 JSON 模式
    )
    
    migrate_llm_config = LLMConfig(
        model="gpt-4o-mini",
        temperature=0,
        json_mode=True  # 组件迁移需要 JSON 模式
    )
    
    logger.info(f"\nLLM 配置:")
    logger.info(f"  - MUI 选择: {select_llm_config.model}")
    logger.info(f"  - 组件迁移: {migrate_llm_config.model}")
    logger.info("")
    
    # 创建迁移团队
    migration_team = MigrationTeam(
        project_name=project_name,
        output_base_dir="outputs",
        select_llm_config=select_llm_config,
        migrate_llm_config=migrate_llm_config
    )
    
    try:
        # 执行页面迁移
        logger.info("开始迁移页面...")
        logger.info("-" * 80)
        
        result = await migration_team.migrate_page(
            page_name=page_name,
            control_json_path=control_json_path,
            output_dir=None  # 使用默认输出目录
        )
        
        logger.info("-" * 80)
        
        # 检查迁移结果
        if result.get("success"):
            logger.info("\n" + "=" * 80)
            logger.info("✅ 页面迁移成功！")
            logger.info("=" * 80)
            logger.info(f"页面名称: {result.get('page_name')}")
            logger.info(f"总组件数: {result.get('total_components')}")
            logger.info(f"已迁移组件: {result.get('migrated_components')}")
            logger.info(f"输出路径: {result.get('output_path')}")
            logger.info("=" * 80)
            
            # 检查输出文件是否存在
            output_path = Path(result.get('output_path', ''))
            if output_path.exists():
                logger.info(f"\n✓ 输出文件已生成: {output_path}")
                logger.info(f"  文件大小: {output_path.stat().st_size} 字节")
                
                # 显示文件的前几行
                try:
                    with open(output_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        logger.info(f"\n输出文件预览 (前 20 行):")
                        logger.info("-" * 80)
                        for i, line in enumerate(lines[:20], 1):
                            logger.info(f"{i:3d}: {line.rstrip()}")
                        if len(lines) > 20:
                            logger.info(f"... (共 {len(lines)} 行)")
                        logger.info("-" * 80)
                except Exception as e:
                    logger.warning(f"无法读取输出文件: {e}")
            else:
                logger.warning(f"⚠ 输出文件不存在: {output_path}")
            
            return True
        else:
            logger.error("\n" + "=" * 80)
            logger.error("❌ 页面迁移失败！")
            logger.error("=" * 80)
            logger.error(f"错误信息: {result.get('error', 'Unknown error')}")
            logger.error("=" * 80)
            return False
            
    except Exception as e:
        logger.error("\n" + "=" * 80)
        logger.error("❌ 迁移过程中发生异常！")
        logger.error("=" * 80)
        logger.error(f"异常类型: {type(e).__name__}")
        logger.error(f"异常信息: {str(e)}")
        logger.error("=" * 80)
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    success = await test_create_expense_report_dialog_box()
    
    if success:
        print("\n✅ 测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 测试失败！")
        sys.exit(1)


# python -m tests.test_single_page_migration
if __name__ == "__main__":
    asyncio.run(main())

