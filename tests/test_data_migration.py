# -*- coding: utf-8 -*-
"""
Data Migration Agent 测试

测试数据资源迁移功能

运行方式：
    python -m tests.test_data_migration
    或
    python tests/test_data_migration.py (从项目根目录运行)
"""

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from src.logger import get_logger
from src.llm import LLMConfig
from src.migration import MigrationTeam, MigrationOrchestrator




async def test_data_migration_with_migration_team():
    """测试使用 MigrationTeam 进行数据迁移"""
    print("\n" + "="*80)
    print("测试: 使用 MigrationTeam 进行数据迁移")
    print("="*80)
    
    # 检查数据资源文件是否存在
    data_resources_file = Path("outputs/ExpenseItDemo/dependency/data_resources.json")
    
    if not data_resources_file.exists():
        print(f"\n⚠ 跳过测试: 数据资源文件不存在")
        print(f"  路径: {data_resources_file}")
        print(f"  提示: 请先运行数据资源解析步骤")
        return
    
    # 读取数据资源文件信息
    with open(data_resources_file, 'r', encoding='utf-8') as f:
        data_resources_data = json.load(f)
    
    print(f"\n数据资源文件: {data_resources_file}")
    print(f"项目名称: {data_resources_data.get('project_name', 'N/A')}")
    print(f"数据资源总数: {data_resources_data.get('total_data_resources', 0)}")
    
    # 显示数据资源详情
    data_resources = data_resources_data.get('data_resources', [])
    if data_resources:
        print(f"\n数据资源列表:")
        for idx, dr in enumerate(data_resources, 1):
            key = dr.get('key', 'N/A')
            tag = dr.get('tag', 'N/A')
            has_deps = 'class_info' in dr and dr['class_info'] is not None
            print(f"  {idx}. {key} ({tag})" + (" [包含依赖类]" if has_deps else ""))
    
    # 创建 LLM 配置
    llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=False)
    
    # 创建迁移团队
    team = MigrationTeam(
        project_name="ExpenseItDemo",
        select_llm_config=llm_config,
        migrate_llm_config=llm_config
    )
    
    # 输出文件路径（使用项目目录）
    output_file = Path("result/ExpenseItDemo/data.ts")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\n输出文件: {output_file}")
    print(f"绝对路径: {output_file.resolve()}")
    
    # 迁移数据资源
    result = await team.migrate_data(
        data_resources_file=str(data_resources_file),
        output_file=str(output_file)
    )
    
    print("\n迁移结果:")
    print(f"  成功: {result['success']}")
    print(f"  消息: {result['message']}")
    print(f"  成功迁移: {result['data_resources_migrated']}")
    print(f"  迁移失败: {result['data_resources_failed']}")
    print(f"  成功迁移的 keys: {result['migrated_keys']}")
    if result['failed_keys']:
        print(f"  失败的 keys: {result['failed_keys']}")
    
    # 检查输出文件是否存在
    output_path = Path(result['output_file'])
    if output_path.exists():
        print(f"\n✓ 输出文件已生成: {output_path}")
        print(f"  绝对路径: {output_path.resolve()}")
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"\n文件大小: {len(content)} 字符")
        print(f"文件行数: {len(content.splitlines())} 行")
        print(f"\n文件内容预览（前1000字符）:")
        print("-" * 60)
        print(content[:1000])
        print("...")
        
        # 检查是否包含依赖类的类型定义（如果有 ExpenseReport）
        if "ExpenseReport" in result['migrated_keys'] or "ExpenseData" in result['migrated_keys']:
            if "LineItem" in content and ("LineItemCollection" in content or "lineItems" in content):
                print("\n✓ 输出文件包含依赖类的类型定义")
            else:
                print("\n⚠ 输出文件可能缺少依赖类的类型定义")
    else:
        print(f"\n✗ 输出文件未生成: {output_path}")
    
    print()


async def test_orchestrator_data_migration():
    """测试通过 MigrationOrchestrator 进行数据迁移"""
    print("\n" + "="*80)
    print("测试: 通过 MigrationOrchestrator 进行数据迁移")
    print("="*80)
    
    # 检查真实数据资源文件是否存在
    data_resources_file = Path("outputs/ExpenseItDemo/dependency/data_resources.json")
    
    if not data_resources_file.exists():
        print(f"\n⚠ 跳过测试: 真实数据资源文件不存在")
        print(f"  路径: {data_resources_file}")
        return
    
    # 创建 LLM 配置
    select_llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=True)
    migrate_llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=True)
    
    # 创建迁移编排器
    orchestrator = MigrationOrchestrator(
        project_name="ExpenseItDemo",
        output_base_dir="outputs",
        select_llm_config=select_llm_config,
        migrate_llm_config=migrate_llm_config
    )
    
    print(f"\n项目名称: ExpenseItDemo")
    print(f"数据资源文件: {orchestrator.data_resources_file}")
    
    # 迁移数据资源
    result = await orchestrator.migrate_data()
    
    print("\n迁移结果:")
    print(f"  成功: {result['success']}")
    print(f"  消息: {result['message']}")
    print(f"  成功迁移: {result['data_resources_migrated']}")
    print(f"  迁移失败: {result['data_resources_failed']}")
    print(f"  输出文件: {result['output_file']}")
    
    # 检查输出文件是否存在
    output_path = Path(result['output_file'])
    if output_path.exists():
        print(f"\n✓ 输出文件已生成: {output_path}")
        print(f"  文件大小: {output_path.stat().st_size} 字节")
    else:
        print(f"\n✗ 输出文件未生成")
    
    print()


def main():
    """主测试函数"""
    # 加载环境变量
    load_dotenv('.env')
    print("✓ 已加载 .env 文件")
    
    print("\n")
    print("="*80)
    print("               数据迁移 Agent 测试")
    print("="*80)
    print("\n")
    
    # 运行所有测试
    tests = [
        ("使用 MigrationTeam 进行数据迁移", test_data_migration_with_migration_team),
        # ("通过 MigrationOrchestrator 进行数据迁移", test_orchestrator_data_migration),
    ]
    
    for idx, (name, test_func) in enumerate(tests, 1):
        try:
            print(f"\n[{idx}/{len(tests)}] 运行测试: {name}")
            asyncio.run(test_func())
            print(f"✓ 测试 '{name}' 完成")
        except Exception as e:
            print(f"✗ 测试 '{name}' 失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*80)
    print("所有测试完成")
    print("="*80)
    print()


# python -m tests.test_data_migration
if __name__ == "__main__":
    main()

