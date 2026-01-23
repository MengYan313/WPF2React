"""
WPF to React 迁移模块

基于多 Agent 协作的迁移系统，提供清晰的架构和可维护性：
- MigrationTeam: 统一的迁移团队入口
- MUISelectAgent: MUI 组件选择 Agent
- ComponentMigrateAgent: 单组件迁移 Agent
- PageMigrateAgent: 页面级协调 Agent
- ResourceMigrateAgent: 资源迁移 Agent
- CsMigrateAgent: C# 文件迁移 Agent
- DataMigrateAgent: 数据资源迁移 Agent
- MigrationOrchestrator: 迁移编排器（协调整个迁移流程）
- migrate_project: 统一入口函数（在 __main__.py 中）
"""

# Agent 架构
from .migration_team import MigrationTeam
from .mui_select_agent import MUISelectAgent
from .component_migrate_agent import ComponentMigrateAgent
from .page_migrate_agent import PageMigrateAgent
from .page_assembly_agent import PageAssemblyAgent
from .resource_migrate_agent import ResourceMigrateAgent
from .cs_migrate_agent import CsMigrateAgent
from .data_migrate_agent import DataMigrateAgent
from .base import BaseMigrationAgent
from .migration_orchestrator import MigrationOrchestrator
from .messages import (
    MUISelectionRequest,
    MUISelectionResponse,
    ComponentMigrationRequest,
    ComponentMigrationResponse,
    PageMigrationRequest,
    PageMigrationResponse,
    PageAssemblyRequest,
    PageAssemblyResponse,
    ResourceMigrationRequest,
    ResourceMigrationResponse,
    CsMigrationRequest,
    CsMigrationResponse,
    BatchCsMigrationRequest,
    BatchCsMigrationResponse,
    DataMigrationRequest,
    DataMigrationResponse
)

# 统一入口函数
from .__main__ import migrate_project

__all__ = [
    # Agent 架构
    'MigrationTeam',
    'MUISelectAgent',
    'ComponentMigrateAgent',
    'PageMigrateAgent',
    'PageAssemblyAgent',
    'ResourceMigrateAgent',
    'CsMigrateAgent',
    'DataMigrateAgent',
    'BaseMigrationAgent',
    'MigrationOrchestrator',
    
    # 统一入口
    'migrate_project',
    
    # 消息类型
    'MUISelectionRequest',
    'MUISelectionResponse',
    'ComponentMigrationRequest',
    'ComponentMigrationResponse',
    'PageMigrationRequest',
    'PageMigrationResponse',
    'PageAssemblyRequest',
    'PageAssemblyResponse',
    'ResourceMigrationRequest',
    'ResourceMigrationResponse',
    'CsMigrationRequest',
    'CsMigrationResponse',
    'BatchCsMigrationRequest',
    'BatchCsMigrationResponse',
    'DataMigrationRequest',
    'DataMigrationResponse',
]
