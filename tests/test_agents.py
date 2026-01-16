# -*- coding: utf-8 -*-
"""
Migration Agents 测试

测试基于 Agent 架构的迁移系统（推荐使用）

运行方式：
    python -m tests.test_agents
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration.agents import MigrationTeam


async def test_simple_component():
    """测试简单组件迁移"""
    print("\n" + "="*80)
    print("测试: 使用 MigrationTeam 迁移单个 Button 组件")
    print("="*80)
    
    # 创建 LLM 配置（使用 gpt-4o-mini + JSON 模式）
    llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=True)
    
    # 创建迁移团队
    team = MigrationTeam(
        project_name="TestProject",
        select_llm_config=llm_config,
        migrate_llm_config=llm_config
    )
    
    # WPF Button 源代码
    wpf_button = """
    <Button 
        Content="Submit Order" 
        Width="150" 
        Height="40"
        Background="#0078D4"
        Foreground="White"
        FontSize="14"
        Click="OnSubmitClick"/>
    """
    
    print("\nWPF 源代码:")
    print(wpf_button)
    
    # 迁移组件
    result = await team.migrate_component(
        wpf_source=wpf_button,
        wpf_tag="Button"
    )
    
    print("\n迁移结果:")
    print(f"  组件名称: {result['component_name']}")
    print(f"  描述: {result.get('description', 'N/A')}")
    print(f"\n  React 代码预览:")
    print("  " + "-" * 60)
    react_code = result['react_code'][:300]
    for line in react_code.split('\n'):
        print(f"  {line}")
    print("  ...")
    print()


async def test_component_with_children():
    """测试带子组件的迁移"""
    print("\n" + "="*80)
    print("测试: 迁移带子组件的 StackPanel")
    print("="*80)
    
    # 创建 LLM 配置（使用 gpt-4o-mini + JSON 模式）
    llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=True)
    
    team = MigrationTeam(
        project_name="TestProject",
        select_llm_config=llm_config,
        migrate_llm_config=llm_config
    )
    
    # WPF StackPanel 源代码
    wpf_stackpanel = """
    <StackPanel Orientation="Vertical" Margin="10">
        <!-- 子组件已迁移 -->
    </StackPanel>
    """
    
    # 假设子组件已经迁移
    children_react = """
    // Child Component: Title
    <Typography variant="h4">Welcome to the App</Typography>
    
    // Child Component: ActionButton
    <Button variant="contained" color="primary" onClick={handleStart}>
        Start Now
    </Button>
    """
    
    print("\nWPF 源代码:")
    print(wpf_stackpanel)
    
    print("\n子组件的 React 代码:")
    print(children_react)
    
    # 迁移组件
    result = await team.migrate_component(
        wpf_source=wpf_stackpanel,
        wpf_tag="StackPanel",
        child_react_code=children_react
    )
    
    print("\n迁移结果:")
    print(f"  组件名称: {result['component_name']}")
    print()


async def test_mui_selection():
    """测试 MUI 组件选择"""
    print("\n" + "="*80)
    print("测试: MUI 组件选择")
    print("="*80)
    
    # 创建 LLM 配置（使用 gpt-4o-mini + JSON 模式）
    llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=True)
    
    team = MigrationTeam(
        project_name="TestProject",
        select_llm_config=llm_config,
        migrate_llm_config=llm_config
    )
    
    # WPF TextBox 源代码
    wpf_textbox = """
    <TextBox 
        Text="{Binding UserName}"
        Width="200"
        Height="30"
        Margin="10"
        Placeholder="Enter your name"/>
    """
    
    print("\nWPF 源代码:")
    print(wpf_textbox)
    
    # 选择 MUI 组件
    result = await team.select_mui_components(
        wpf_source=wpf_textbox,
        wpf_tag="TextBox",
        max_components=3
    )
    
    print("\n选择结果:")
    print(f"  选中组件: {', '.join(result['selected_components'])}")
    print(f"  选择理由: {result['reasoning']}")
    print()


async def test_page_migration():
    """测试页面迁移（如果有测试数据）"""
    print("\n" + "="*80)
    print("测试: 完整页面迁移（MainWindow）")
    print("="*80)
    
    # 检查测试数据是否存在
    control_json_path = "outputs/ExpenseItDemo/dependency/control_MainWindow.json"
    
    if not Path(control_json_path).exists():
        print(f"\n⚠ 跳过页面迁移测试: 测试数据文件不存在")
        print(f"  路径: {control_json_path}")
        return
    
    # 创建 LLM 配置（使用 gpt-4o-mini + JSON 模式）
    llm_config = LLMConfig(model="gpt-4o-mini", temperature=0, json_mode=True)
    
    # 创建迁移团队
    team = MigrationTeam(
        project_name="ExpenseItDemo",
        select_llm_config=llm_config,
        migrate_llm_config=llm_config
    )
    
    print(f"\n加载文件: {control_json_path}")
    
    # 迁移页面
    result = await team.migrate_page(
        page_name="MainWindow",
        control_json_path=control_json_path
    )
    
    print(f"\n迁移统计:")
    print(f"  总组件数: {result.get('total_components', 0)}")
    print(f"  已迁移组件: {result.get('migrated_components', 0)}")
    print(f"  输出路径: {result.get('output_path', 'N/A')}")
    print()


def main():
    """主测试函数"""
    # 加载环境变量
    load_dotenv('.env')
    print("✓ 已加载 .env 文件")
    
    print("\n")
    print("="*80)
    print("               迁移 Agent 系统测试")
    print("="*80)
    print("\n")
    
    # 运行所有测试
    tests = [
        ("简单组件迁移", test_simple_component),
        ("带子组件的迁移", test_component_with_children),
        ("MUI 组件选择", test_mui_selection),
        ("完整页面迁移", test_page_migration),
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


# python -m tests.test_agents
if __name__ == "__main__":
    main()
