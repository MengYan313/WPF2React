"""
WPF to React 迁移模块

本模块使用 src.llm 包提供的通用 LLM 框架，
实现 WPF 应用到 React 应用的自动化迁移。

## 推荐使用 Agent 架构（新）

基于多 Agent 协作的迁移系统，提供更好的可读性和可维护性：
- MigrationTeam: 统一的迁移团队入口
- MUISelectAgent: MUI 组件选择 Agent
- ComponentMigrateAgent: 单组件迁移 Agent
- PageMigrateAgent: 页面级协调 Agent

## 传统类（已有）

功能模块：
- component_mig: 单个 WPF 组件迁移
- page_mig: 整个 XAML 页面迁移（递归处理组件树）
- mui_selector: MUI 组件智能选择器
"""

# Agent 架构（推荐）
from .agents import (
    MigrationTeam,
    MUISelectAgent,
    ComponentMigrateAgent,
    PageMigrateAgent
)

# 传统类（向后兼容）
from .component_mig import ComponentMigrator
from .page_mig import PageMigrator
from .mui_selector import MUIComponentSelector

__all__ = [
    # Agent 架构（推荐）
    'MigrationTeam',
    'MUISelectAgent',
    'ComponentMigrateAgent',
    'PageMigrateAgent',
    
    # 传统类（向后兼容）
    'ComponentMigrator',
    'PageMigrator',
    'MUIComponentSelector',
]
