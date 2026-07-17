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

from importlib import import_module

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

_EXPORTS = {
    "MigrationTeam": (".migration_team", "MigrationTeam"),
    "MUISelectAgent": (".mui_select_agent", "MUISelectAgent"),
    "ComponentMigrateAgent": (".component_migrate_agent", "ComponentMigrateAgent"),
    "PageMigrateAgent": (".page_migrate_agent", "PageMigrateAgent"),
    "PageAssemblyAgent": (".page_assembly_agent", "PageAssemblyAgent"),
    "ResourceMigrateAgent": (".resource_migrate_agent", "ResourceMigrateAgent"),
    "CsMigrateAgent": (".cs_migrate_agent", "CsMigrateAgent"),
    "DataMigrateAgent": (".data_migrate_agent", "DataMigrateAgent"),
    "BaseMigrationAgent": (".base", "BaseMigrationAgent"),
    "MigrationOrchestrator": (".migration_orchestrator", "MigrationOrchestrator"),
    "migrate_project": (".__main__", "migrate_project"),
}
_EXPORTS.update({name: (".messages", name) for name in __all__ if name.endswith(("Request", "Response"))})


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
