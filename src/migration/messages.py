# -*- coding: utf-8 -*-
"""
Migration Agent Message Types

定义 Agent 之间通信使用的消息类型。
使用 Pydantic BaseModel 以支持 Optional 类型（Autogen 要求）。
"""

from typing import List
from pydantic import BaseModel


class MUISelectionRequest(BaseModel):
    """
    MUI 组件选择请求
    
    发送给 MUISelectAgent，请求选择合适的 MUI 组件。
    """
    wpf_source: str  # WPF 组件源代码
    wpf_tag: str  # WPF 组件标签名（如 Button, TextBox）
    max_components: int = 3  # 最多选择的组件数量


class MUISelectionResponse(BaseModel):
    """
    MUI 组件选择响应
    
    MUISelectAgent 返回的结果。
    """
    selected_components: List[str]  # 选中的 MUI 组件名称列表
    docs: str  # 合并后的 MUI 组件文档
    reasoning: str  # 选择理由


class ComponentMigrationRequest(BaseModel):
    """
    组件迁移请求
    
    发送给 ComponentMigrateAgent，请求迁移一个 WPF 组件。
    """
    wpf_source: str  # WPF 组件源代码
    dependencies_code: str  # 依赖代码（如 ViewModel）
    child_react_code: str  # 子组件的 React 代码
    mui_components_docs: str  # 相关 MUI 组件文档


class ComponentMigrationResponse(BaseModel):
    """
    组件迁移响应
    
    ComponentMigrateAgent 返回的结果。
    """
    component_name: str  # 组件名称
    description: str  # 组件描述
    imports: List[str]  # 导入语句
    interfaces: str  # TypeScript 接口定义
    react_code: str  # React 组件代码
    migration_notes: str  # 迁移说明


class PageMigrationRequest(BaseModel):
    """
    页面迁移请求
    
    发送给 PageMigrateAgent，请求迁移整个页面。
    """
    control_json_path: str | None = None  # 控件依赖 JSON 文件路径
    page_name: str  # 页面名称
    output_dir: str | None = None  # 输出目录


class PageMigrationResponse(BaseModel):
    """
    页面迁移响应
    
    PageMigrateAgent 返回的结果。
    """
    page_name: str  # 页面名称
    total_components: int  # 总组件数
    migrated_components: int  # 已迁移组件数
    output_path: str  # 输出文件路径
    success: bool  # 是否成功
    error: str | None = None  # 错误信息（如果有）


class PageAssemblyRequest(BaseModel):
    """
    页面整合请求
    
    将已迁移的根组件整合成完整的 React 页面。
    """
    page_name: str  # 页面名称（最终导出的组件名必须与此相同）
    page_layout_description: str  # 页面布局描述（自然语言，不涉及 WPF 组件名）
    root_component: str  # 已迁移的根组件代码
    root_component_name: str  # 根组件名称
    root_imports: List[str]  # 根组件的 imports
    root_interfaces: str  # 根组件的 interfaces


class PageAssemblyResponse(BaseModel):
    """
    页面整合响应
    
    返回整合后的完整页面代码。
    """
    page_code: str  # 完整的页面 TypeScript 代码
    page_description: str  # 页面描述
    assembly_notes: str  # 整合说明
