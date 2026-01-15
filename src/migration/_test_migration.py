# -*- coding: utf-8 -*-
"""
迁移模块测试示例

演示如何使用 ComponentMigrator 和 PageMigrator
"""

import asyncio
from pathlib import Path

from .component_mig import ComponentMigrator
from .page_mig import PageMigrator


async def test_1_simple_component():
    """测试 1: 简单组件迁移"""
    print("=" * 60)
    print("测试 1: 单个简单组件迁移")
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
    
    migrator = ComponentMigrator()
    
    print("\nWPF 源代码:")
    print(wpf_source)
    
    print("\n正在调用 LLM 迁移...")
    result = await migrator.migrate(wpf_source=wpf_source)
    
    print(f"\n✓ 迁移完成!")
    print(f"  组件名称: {result['component_name']}")
    print(f"  描述: {result.get('description', 'N/A')}")
    print(f"\n  React 代码:\n{result['react_code']}")
    
    if result.get('migration_notes'):
        print(f"\n  迁移说明: {result['migration_notes']}")
    
    print()


async def test_2_component_with_children():
    """测试 2: 带子组件的迁移"""
    print("=" * 60)
    print("测试 2: 带子组件的组件迁移")
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
    
    migrator = ComponentMigrator()
    
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
    print(f"\n  React 代码:\n{result['react_code']}")
    print()


async def test_3_page_migration():
    """测试 3: 完整页面迁移（从 control JSON）"""
    print("=" * 60)
    print("测试 3: 完整页面迁移（MainWindow）")
    print("=" * 60)
    
    # 检查 control JSON 文件是否存在
    control_file = Path("outputs/ExpenseItDemo/dependency/control_MainWindow.json")
    
    if not control_file.exists():
        print(f"\n⚠ 测试文件不存在: {control_file}")
        print("请先运行依赖分析生成 control JSON 文件")
        print()
        return
    
    # 创建页面迁移器
    page_migrator = PageMigrator(
        project_name="ExpenseItDemo",
        output_base_dir="outputs"
    )
    
    # 迁移整个页面
    try:
        result = await page_migrator.migrate_page_from_control_json(
            control_json_path=str(control_file)
        )
        
        print(f"✓ 页面迁移完成!")
        print(f"  根组件: {result['component_name']}")
        print(f"  描述: {result.get('description', 'N/A')}")
        print(f"  WPF 标签: {result.get('wpf_tag', 'N/A')}")
        print(f"  节点路径: {result.get('node_path', 'N/A')}")
        
        # 显示统计信息
        all_components = page_migrator.get_all_components()
        print(f"\n统计信息:")
        print(f"  总共迁移组件数: {len(all_components)}")
        
        # 显示所有组件的路径和名称
        print(f"\n  组件列表:")
        for path, comp in sorted(all_components.items()):
            wpf_tag = comp.get('wpf_tag', 'Unknown')
            react_name = comp.get('component_name', 'Unknown')
            print(f"    {path:20s} {wpf_tag:15s} -> {react_name}")
        
        print()
        
    except Exception as e:
        print(f"\n✗ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        print()


async def test_4_page_migration_by_name():
    """测试 4: 使用页面名称迁移"""
    print("=" * 60)
    print("测试 4: 使用页面名称迁移（简化方式）")
    print("=" * 60)
    
    page_migrator = PageMigrator(
        project_name="ExpenseItDemo",
        output_base_dir="outputs"
    )
    
    # 直接使用页面名称
    page_name = "MainWindow"
    
    try:
        print(f"\n迁移页面: {page_name}")
        result = await page_migrator.migrate_page(page_name=page_name)
        
        print(f"\n✓ 迁移完成!")
        print(f"  根组件: {result['component_name']}")
        
        # 检查特定节点
        specific_path = "root.1.1"  # 例如某个特定节点
        specific_component = page_migrator.get_component_by_path(specific_path)
        
        if specific_component:
            print(f"\n  示例节点 ({specific_path}):")
            print(f"    WPF: {specific_component.get('wpf_tag', 'Unknown')}")
            print(f"    React: {specific_component.get('component_name', 'Unknown')}")
        
        print()
        
    except FileNotFoundError as e:
        print(f"\n⚠ {e}")
        print()
    except Exception as e:
        print(f"\n✗ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        print()


async def test_5_migration_output_files():
    """测试 5: 检查迁移输出文件"""
    print("=" * 60)
    print("测试 5: 检查迁移输出文件")
    print("=" * 60)
    
    migration_dir = Path("outputs/ExpenseItDemo/migration")
    
    if not migration_dir.exists():
        print(f"\n⚠ 迁移目录不存在: {migration_dir}")
        print("请先运行测试 3 或 4 生成迁移文件")
        print()
        return
    
    print(f"\n迁移输出目录: {migration_dir}")
    print("\n文件列表:")
    
    files = sorted(migration_dir.glob("*"))
    for file in files:
        size_kb = file.stat().st_size / 1024
        print(f"  {file.name:40s} ({size_kb:.1f} KB)")
    
    # 读取并显示 .tree.json 文件内容
    tree_files = list(migration_dir.glob("*.tree.json"))
    if tree_files:
        tree_file = tree_files[0]
        print(f"\n组件树结构 ({tree_file.name}):")
        
        import json
        with open(tree_file, 'r', encoding='utf-8') as f:
            tree_data = json.load(f)
        
        def print_tree(node, indent=0):
            """递归打印树结构"""
            prefix = "  " * indent
            component_name = node.get('component_name', 'Unknown')
            wpf_tag = node.get('wpf_tag', 'Unknown')
            path = node.get('path', '')
            print(f"{prefix}- [{path}] {wpf_tag} -> {component_name}")
            
            for child in node.get('children', []):
                print_tree(child, indent + 1)
        
        print_tree(tree_data)
    
    print()


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print(" " * 18 + "迁移模块测试")
    print("=" * 60 + "\n")
    
    tests = [
        ("简单组件迁移", test_1_simple_component),
        ("带子组件的迁移", test_2_component_with_children),
        ("完整页面迁移", test_3_page_migration),
        # ("按名称迁移页面", test_4_page_migration_by_name),  # 与测试3重复，跳过
        ("检查输出文件", test_5_migration_output_files),
    ]
    
    for i, (name, test_func) in enumerate(tests, 1):
        print(f"运行测试 {i}/{len(tests)}: {name}")
        try:
            await test_func()
        except Exception as e:
            print(f"\n✗ 测试失败: {e}\n")
            import traceback
            traceback.print_exc()
    
    print("=" * 60)
    print("所有测试完成")
    print("=" * 60)


if __name__ == "__main__":
    # 加载环境变量
    try:
        from dotenv import load_dotenv, find_dotenv
        env_file = find_dotenv()
        if env_file:
            load_dotenv(env_file)
            print("✓ 已加载 .env 文件\n")
    except ImportError:
        print("⚠ python-dotenv 未安装\n")
    
    # 运行测试
    asyncio.run(main())
