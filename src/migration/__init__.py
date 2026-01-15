"""
WPF to React 迁移模块

本模块使用 src.llm 包提供的通用 LLM 框架，
实现 WPF 应用到 React 应用的自动化迁移。

功能模块：
- component_mig: 单个 WPF 组件迁移
- page_mig: 整个 XAML 页面迁移（递归处理组件树）
- mui_selector: MUI 组件智能选择器
"""

from .component_mig import ComponentMigrator
from .page_mig import PageMigrator
from .mui_selector import MUIComponentSelector

__all__ = [
    'ComponentMigrator',
    'PageMigrator',
    'MUIComponentSelector',
]
