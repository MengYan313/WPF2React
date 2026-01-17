"""
WPF to React 迁移模块

基于多 Agent 协作的迁移系统，提供清晰的架构和可维护性：
- MigrationTeam: 统一的迁移团队入口
- MUISelectAgent: MUI 组件选择 Agent
- ComponentMigrateAgent: 单组件迁移 Agent
- PageMigrateAgent: 页面级协调 Agent
"""

# Agent 架构
from .migration_team import MigrationTeam
from .mui_select_agent import MUISelectAgent
from .component_migrate_agent import ComponentMigrateAgent
from .page_migrate_agent import PageMigrateAgent
from .base import BaseMigrationAgent
from .messages import (
    MUISelectionRequest,
    MUISelectionResponse,
    ComponentMigrationRequest,
    ComponentMigrationResponse,
    PageMigrationRequest,
    PageMigrationResponse,
    PageAssemblyRequest,
    PageAssemblyResponse
)

__all__ = [
    # Agent 架构
    'MigrationTeam',
    'MUISelectAgent',
    'ComponentMigrateAgent',
    'PageMigrateAgent',
    'BaseMigrationAgent',
    
    # 消息类型
    'MUISelectionRequest',
    'MUISelectionResponse',
    'ComponentMigrationRequest',
    'ComponentMigrationResponse',
    'PageMigrationRequest',
    'PageMigrationResponse',
    'PageAssemblyRequest',
    'PageAssemblyResponse',
]
