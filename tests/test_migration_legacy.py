# -*- coding: utf-8 -*-
"""
迁移模块测试 - 传统类版本

测试 ComponentMigrator 和 PageMigrator（传统实现）

运行方式：
    python -m tests.test_migration_legacy
"""

import asyncio
from pathlib import Path

from src.llm import LLMConfig
from src.migration import ComponentMigrator, PageMigrator


async def test_simple_component():
    """测试简单组件迁移"""
    print("=" * 60)
    print("测试: 单个简单组件迁移")
    print("=" * 60)
    
    # WPF Button 示例
    wpf_source = """
    <Button 
        Content="Click Me" 
        Width="120" 
        Height="40"
        Background="#0078D4"
        Foreground="White"
        Click="Button_Click"/>
    """
    
    # 使用 gpt-4o-mini + JSON 模式
    llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=True)
    migrator = ComponentMigrator(llm_config=llm_config)
    
    print("\nWPF 源代码:")
    print(wpf_source)
    
    print("\n正在调用 LLM 迁移...")
    result = await migrator.migrate(wpf_source=wpf_source)
    
    print(f"\n✓ 迁移完成!")
    print(f"  组件名称: {result['component_name']}")
    print(f"  描述: {result.get('description', 'N/A')}")
    print(f"\n  React 代码预览:\n{result['react_code'][:200]}...")
    print()


async def test_component_with_children():
    """测试带子组件的迁移"""
    print("=" * 60)
    print("测试: 带子组件的组件迁移")
    print("=" * 60)
    
    # WPF StackPanel 示例
    wpf_source = """
    <StackPanel Orientation="Vertical" Margin="10">
        <!-- 子组件已迁移 -->
    </StackPanel>
    """
    
    # 假设子组件已经迁移完成
    children_react_code = """
    // Child Component: WelcomeText
    <Typography variant="h4">Welcome to the App</Typography>
    
    // Child Component: StartButton
    <Button variant="contained" color="primary" onClick={handleStart}>
        Get Started
    </Button>
    """
    
    # 使用 gpt-4o-mini + JSON 模式
    llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=True)
    migrator = ComponentMigrator(llm_config=llm_config)
    
    print("\nWPF 源代码:")
    print(wpf_source)
    print("\n子组件的 React 代码:")
    print(children_react_code[:100] + "...")
    
    print("\n正在调用 LLM 迁移...")
    result = await migrator.migrate(
        wpf_source=wpf_source,
        children_react_code=children_react_code
    )
    
    print(f"\n✓ 迁移完成!")
    print(f"  组件名称: {result['component_name']}")
    print()


async def test_page_migration():
    """测试完整页面迁移"""
    print("=" * 60)
    print("测试: 完整页面迁移（MainWindow）")
    print("=" * 60)
    
    # 检查 control JSON 文件是否存在
    control_file = Path("outputs/ExpenseItDemo/dependency/control_MainWindow.json")
    
    if not control_file.exists():
        print(f"\n⚠ 测试文件不存在: {control_file}")
        print("请先运行依赖分析生成 control JSON 文件")
        print()
        return
    
    # 使用 gpt-4o-mini + JSON 模式
    llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=True)
    
    # 创建页面迁移器
    page_migrator = PageMigrator(
        project_name="ExpenseItDemo",
        output_base_dir="outputs",
        llm_config=llm_config
    )
    
    # 迁移整个页面
    try:
        result = await page_migrator.migrate_page_from_control_json(
            control_json_path=str(control_file)
        )
        
        print(f"✓ 页面迁移完成!")
        print(f"  根组件: {result['component_name']}")
        print(f"  WPF 标签: {result.get('wpf_tag', 'N/A')}")
        
        # 显示统计信息
        all_components = page_migrator.get_all_components()
        print(f"\n统计信息:")
        print(f"  总共迁移组件数: {len(all_components)}")
        print()
        
    except Exception as e:
        print(f"\n✗ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        print()


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print(" " * 15 + "迁移模块测试（传统类）")
    print("=" * 60 + "\n")
    
    tests = [
        ("简单组件迁移", test_simple_component),
        ("带子组件的迁移", test_component_with_children),
        ("完整页面迁移", test_page_migration),
    ]
    
    for i, (name, test_func) in enumerate(tests, 1):
        print(f"\n[{i}/{len(tests)}] 运行测试: {name}")
        try:
            await test_func()
        except Exception as e:
            print(f"\n✗ 测试失败: {e}\n")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("所有测试完成")
    print("=" * 60)


# python -m tests.test_migration_legacy
if __name__ == "__main__":
    # 加载环境变量
    try:
        from dotenv import load_dotenv
        load_dotenv('.env')
        print("✓ 已加载 .env 文件\n")
    except ImportError:
        print("⚠ python-dotenv 未安装\n")
    except Exception as e:
        print(f"⚠ 加载 .env 文件失败: {e}\n")
    
    # 运行测试
    asyncio.run(main())

