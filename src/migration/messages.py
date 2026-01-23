# -*- coding: utf-8 -*-
"""
Migration Agent Message Types

定义 Agent 之间通信使用的消息类型。
使用 Pydantic BaseModel 以支持 Optional 类型（Autogen 要求）。
"""

from typing import List, Dict, Any
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
    docs: List[str]  # 使用示例列表，与 selected_components 一一对应


class ComponentMigrationRequest(BaseModel):
    """
    组件迁移请求
    
    发送给 ComponentMigrateAgent，请求迁移一个 WPF 组件。
    """
    wpf_source: str  # WPF 组件源代码
    child_react_code: str  # 子组件的 React 代码
    mui_components_docs: str  # MUI 组件名和使用示例的配对列表，格式: [ComponentName]\nusage_example\n[/ComponentName]
    template: str = ""  # 依赖的模板代码（DataTemplate/ControlTemplate 等）
    data: Dict[str, Any] = {}  # 依赖的数据资源（从 data_resources.json 中提取）


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
    page_source: str  # 完整的 WPF 页面源代码（XAML）
    page_layout_description: str  # 页面布局描述（自然语言，不涉及 WPF 组件名）
    child_page_references: str  # 子页面引用分析
    direct_dependencies: List[str]  # 直接依赖页面列表
    root_component: str  # 已迁移的根组件代码
    root_component_name: str  # 根组件名称
    root_imports: List[str]  # 根组件的 imports
    root_interfaces: str  # 根组件的 interfaces
    template: str = ""  # 根节点的模板代码（DataTemplate/ControlTemplate 等）
    data: Dict[str, Any] = {}  # 根节点的数据资源（从 data_resources.json 中提取）


class PageAssemblyResponse(BaseModel):
    """
    页面整合响应
    
    返回整合后的完整页面代码。
    """
    page_code: str  # 完整的页面 TypeScript 代码
    page_description: str  # 页面描述
    assembly_notes: str  # 整合说明


class ResourceMigrationRequest(BaseModel):
    """
    资源迁移请求
    
    发送给 ResourceMigrateAgent，请求迁移项目资源文件。
    """
    project_name: str  # 项目名称
    resource_dependency_file: str  # 资源依赖文件路径
    resources_dir: str  # 资源输出目录


class ResourceMigrationResponse(BaseModel):
    """
    资源迁移响应
    
    ResourceMigrateAgent 返回的结果。
    """
    success: bool  # 是否成功
    message: str  # 消息
    resources_migrated: int  # 成功迁移的资源数
    resources_failed: int  # 迁移失败的资源数
    migrated_files: List[str]  # 成功迁移的文件列表
    failed_files: List[str]  # 失败的文件列表
    resources_dir: str  # 资源目录路径


class CsMigrationRequest(BaseModel):
    """
    C# 文件迁移请求
    
    发送给 CsMigrateAgent，请求迁移单个 C# 文件。
    """
    file_name: str  # 文件名（不含扩展名）
    cs_file_path: str  # C# 源文件路径
    dependencies: List[str]  # 依赖的文件名列表
    defined_types: List[str]  # 文件中定义的类型
    output_dir: str  # 输出目录
    ts_info_file: str  # ts_info.json 文件路径


class CsMigrationResponse(BaseModel):
    """
    C# 文件迁移响应
    
    CsMigrateAgent 返回的结果。
    """
    success: bool  # 是否成功
    file_name: str  # 文件名
    output_file: str  # 输出文件路径
    ts_info: Dict[str, Any] | None = None  # TypeScript 文件分析信息
    error: str | None = None  # 错误信息（如果有）


class BatchCsMigrationRequest(BaseModel):
    """
    批量 C# 文件迁移请求
    
    发送给 CsMigrateAgent，请求批量迁移 C# 文件。
    """
    project_name: str  # 项目名称
    cs_dependency_file: str  # C# 依赖文件路径
    output_dir: str  # 输出目录
    ts_info_file: str  # ts_info.json 文件路径


class BatchCsMigrationResponse(BaseModel):
    """
    批量 C# 文件迁移响应
    
    CsMigrateAgent 返回的结果。
    """
    success: bool  # 是否成功
    message: str  # 消息
    files_migrated: int  # 成功迁移的文件数
    files_failed: int  # 迁移失败的文件数
    migrated_files: List[str]  # 成功迁移的文件列表
    failed_files: List[str]  # 失败的文件列表
    output_dir: str  # 输出目录


class DataMigrationRequest(BaseModel):
    """
    数据迁移请求
    
    发送给 DataMigrateAgent，请求迁移项目数据资源。
    """
    project_name: str  # 项目名称
    data_resources_file: str  # 数据资源文件路径
    output_file: str  # 输出文件路径（result/{project_name}/data.ts）


class DataMigrationResponse(BaseModel):
    """
    数据迁移响应
    
    DataMigrateAgent 返回的结果。
    """
    success: bool  # 是否成功
    message: str  # 消息
    data_resources_migrated: int  # 成功迁移的数据资源数
    data_resources_failed: int  # 迁移失败的数据资源数
    migrated_keys: List[str]  # 成功迁移的数据资源 key 列表
    failed_keys: List[str]  # 失败的数据资源 key 列表
    output_file: str  # 输出文件路径
