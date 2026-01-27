# -*- coding: utf-8 -*-
"""
C# Migration Agent 测试

测试单个 C# 文件迁移功能

运行方式：
    python -m tests.test_cs_migration
    或
    python tests/test_cs_migration.py (从项目根目录运行)
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from src.llm import LLMConfig
from src.migration.cs_migrate_agent import CsMigrateAgent


# 加载环境变量
load_dotenv()


async def test_single_cs_file_migration():
    """测试单个 C# 文件迁移"""
    print("\n" + "="*80)
    print("测试: 单个 C# 文件迁移")
    print("="*80)
    
    # 测试文件路径
    cs_file_path = Path("repos/ExpenseItDemo/LineItem.cs")
    # cs_file_path = Path("repos/ExpenseItDemo/Validation/NumberValidationrule.cs")
    
    if not cs_file_path.exists():
        print(f"\n⚠ 跳过测试: C# 文件不存在")
        print(f"  路径: {cs_file_path}")
        return None
    
    # 创建临时输出目录
    output_dir = Path("tests/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建 CsMigrateAgent 实例（使用内部方法，简化配置）
    agent = CsMigrateAgent(
        project_name="ExpenseItDemo",
        output_base_dir="tests/output",
        llm_config=LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=False)
    )
    
    print(f"\nC# 源文件: {cs_file_path}")
    print(f"输出目录: {output_dir}")
    
    # 调用内部方法进行迁移
    result = await agent._migrate_single_cs_file(
        file_name="LineItem",
        cs_file_path=str(cs_file_path),
        dependencies=[],
        defined_types=["LineItem"],
        output_dir=str(output_dir),
        ts_info_file=str(output_dir / "ts_info.json"),
        dependency_contents={}
    )
    
    # 检查结果
    print("\n" + "="*80)
    print("迁移结果:")
    print("="*80)
    
    if result.get('success'):
        print(f"✅ 迁移成功")
        print(f"  输出文件: {result.get('output_file')}")
        
        # 验证输出文件
        output_file = Path(result.get('output_file', ''))
        if output_file.exists():
            content = output_file.read_text(encoding='utf-8')
            
            # 检查是否包含标记
            if "[TypeScript Code]" in content or "[/TypeScript Code]" in content:
                print("\n⚠ 警告: 输出文件仍包含标记！")
            else:
                print("\n✅ 输出文件格式正确（无标记）")
            
            # 显示前10行
            lines = content.split('\n')
            print(f"\n输出文件内容（前10行）:")
            print("-" * 80)
            for i, line in enumerate(lines[:10], 1):
                print(f"{i:3}: {line}")
            if len(lines) > 10:
                print(f"... (共 {len(lines)} 行)")
            print("-" * 80)
    else:
        print(f"❌ 迁移失败")
        print(f"  错误: {result.get('error', 'Unknown error')}")
    
    print("="*80)
    return result


async def main():
    """主函数"""
    try:
        result = await test_single_cs_file_migration()
        
        if result and result.get('success'):
            print("\n✅ 测试通过")
            sys.exit(0)
        else:
            print("\n❌ 测试失败")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)



# python -m tests.test_cs_migration
if __name__ == "__main__":
    asyncio.run(main())

