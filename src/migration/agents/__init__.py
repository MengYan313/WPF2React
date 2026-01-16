# -*- coding: utf-8 -*-
"""
Migration Agents Package

基于 Autogen 官方 API 的多 Agent 迁移架构。
"""

from .base import BaseMigrationAgent
from .messages import (
    MUISelectionRequest,
    MUISelectionResponse,
    ComponentMigrationRequest,
    ComponentMigrationResponse,
    PageMigrationRequest,
    PageMigrationResponse
)
from .mui_select_agent import MUISelectAgent
from .component_migrate_agent import ComponentMigrateAgent
from .page_migrate_agent import PageMigrateAgent
from .migration_team import MigrationTeam

__all__ = [
    # Base
    "BaseMigrationAgent",
    
    # Messages
    "MUISelectionRequest",
    "MUISelectionResponse",
    "ComponentMigrationRequest",
    "ComponentMigrationResponse",
    "PageMigrationRequest",
    "PageMigrationResponse",
    
    # Agents
    "MUISelectAgent",
    "ComponentMigrateAgent",
    "PageMigrateAgent",
    
    # Team
    "MigrationTeam"
]
