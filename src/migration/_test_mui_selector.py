# -*- coding: utf-8 -*-
"""
MUI 组件选择器测试文件
"""

import asyncio
from mui_selector import MUIComponentSelector


async def test_select_button_component():
    """测试为 Button 组件选择 MUI 组件"""
    print("\n" + "="*80)
    print("测试 1: 为 WPF Button 选择 MUI 组件")
    print("="*80)
    
    selector = MUIComponentSelector()
    
    wpf_button_source = """
<Button Content="Submit" 
        Width="100" 
        Height="30"
        Background="Blue"
        Foreground="White"
        Click="OnSubmitClick"/>
"""
    
    selected = await selector.select_mui_components(
        wpf_source=wpf_button_source,
        wpf_tag="Button"
    )
    
    print(f"✓ 选择的 MUI 组件: {selected}")
    assert len(selected) > 0, "应该至少选择一个组件"
    print("✓ 测试通过\n")


async def test_select_grid_component():
    """测试为 Grid 组件选择 MUI 组件"""
    print("\n" + "="*80)
    print("测试 2: 为 WPF Grid 选择 MUI 组件")
    print("="*80)
    
    selector = MUIComponentSelector()
    
    wpf_grid_source = """
<Grid>
    <Grid.RowDefinitions>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="*"/>
    </Grid.RowDefinitions>
    <Grid.ColumnDefinitions>
        <ColumnDefinition Width="200"/>
        <ColumnDefinition Width="*"/>
    </Grid.ColumnDefinitions>
</Grid>
"""
    
    selected = await selector.select_mui_components(
        wpf_source=wpf_grid_source,
        wpf_tag="Grid"
    )
    
    print(f"✓ 选择的 MUI 组件: {selected}")
    assert len(selected) > 0, "应该至少选择一个组件"
    print("✓ 测试通过\n")


async def test_get_full_docs():
    """测试获取完整的 MUI 文档"""
    print("\n" + "="*80)
    print("测试 3: 获取完整的 MUI 组件文档")
    print("="*80)
    
    selector = MUIComponentSelector()
    
    wpf_textbox_source = """
<TextBox Text="{Binding UserName}"
         Width="200"
         Height="25"
         Margin="5"/>
"""
    
    docs = await selector.get_mui_docs_for_wpf(
        wpf_source=wpf_textbox_source,
        wpf_tag="TextBox"
    )
    
    print(f"✓ 获取的文档长度: {len(docs)} 字符")
    assert len(docs) > 0, "应该返回非空文档"
    
    # 检查文档是否包含 "# MUI Component:"
    assert "# MUI Component:" in docs, "文档应该包含组件标题"
    print("✓ 测试通过\n")


async def test_selector_with_complex_component():
    """测试复杂组件的选择"""
    print("\n" + "="*80)
    print("测试 4: 为复杂 WPF 组件选择 MUI 组件")
    print("="*80)
    
    selector = MUIComponentSelector()
    
    wpf_listview_source = """
<ListView ItemsSource="{Binding Items}">
    <ListView.View>
        <GridView>
            <GridViewColumn Header="Name" DisplayMemberBinding="{Binding Name}"/>
            <GridViewColumn Header="Price" DisplayMemberBinding="{Binding Price}"/>
            <GridViewColumn Header="Quantity" DisplayMemberBinding="{Binding Quantity}"/>
        </GridView>
    </ListView.View>
</ListView>
"""
    
    selected = await selector.select_mui_components(
        wpf_source=wpf_listview_source,
        wpf_tag="ListView"
    )
    
    print(f"✓ 选择的 MUI 组件: {selected}")
    assert len(selected) > 0, "应该至少选择一个组件"
    assert len(selected) <= 3, "最多应该选择 3 个组件"
    print("✓ 测试通过\n")


async def main():
    """运行所有测试"""
    print("\n" + "="*80)
    print("MUI 组件选择器测试套件")
    print("="*80)
    
    try:
        await test_select_button_component()
        await test_select_grid_component()
        await test_get_full_docs()
        await test_selector_with_complex_component()
        
        print("\n" + "="*80)
        print("✓ 所有测试通过!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

