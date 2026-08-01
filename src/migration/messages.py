"""迁移 Agent 之间传递的强类型消息。"""

from typing import Any

from pydantic import BaseModel, Field


class MUISelectionRequest(BaseModel):
    """MUI 组件选择请求。"""

    wpf_source: str
    wpf_tag: str
    max_components: int = 3
    attributes: dict[str, Any] = Field(default_factory=dict)
    semantic_references: list[dict[str, Any]] = Field(default_factory=list)
    classification: str = ""


class MUISelectionResponse(BaseModel):
    """MUI 组件选择结果，组件名与文档按下标对应。"""

    selected_components: list[str]
    docs: list[str]
    retrieval_strategy: str = "unresolved"
    confidence: float = 0.0
    candidate_scores: list[float] = Field(default_factory=list)
    query_description: str = ""


class ComponentMigrationRequest(BaseModel):
    """单个 WPF 组件迁移请求。"""

    wpf_source: str
    child_react_code: str
    mui_components_docs: str
    template: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ComponentMigrationResponse(BaseModel):
    """单个组件的 React 迁移结果。"""

    component_name: str
    imports: list[str]
    interfaces: str
    react_code: str


class PageMigrationRequest(BaseModel):
    """完整页面迁移请求。"""

    control_json_path: str | None = None
    page_id: str
    component_name: str
    output_dir: str | None = None


class PageMigrationResponse(BaseModel):
    """完整页面迁移结果。"""

    page_id: str
    component_name: str
    total_components: int
    migrated_components: int
    output_path: str
    success: bool
    error: str | None = None


class PageAssemblyRequest(BaseModel):
    """把已迁移根组件组装为完整页面。"""

    page_id: str
    component_name: str
    page_source: str
    page_layout_description: str
    child_page_references: str
    direct_dependencies: list[str]
    root_component: str
    template: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class PageAssemblyResponse(BaseModel):
    """页面组装结果。"""

    page_code: str
    page_description: str
    assembly_notes: str


class ResourceMigrationRequest(BaseModel):
    """静态资源迁移请求。"""

    project_name: str
    resource_dependency_file: str
    resources_dir: str


class ResourceMigrationResponse(BaseModel):
    """静态资源迁移结果。"""

    success: bool
    message: str
    resources_migrated: int
    resources_failed: int
    migrated_files: list[str]
    failed_files: list[str]
    resources_dir: str


class CsMigrationRequest(BaseModel):
    """单个 C# 文件迁移请求。"""

    file_name: str
    cs_file_path: str
    dependencies: list[str]
    defined_types: list[str]
    output_dir: str
    ts_info_file: str


class CsMigrationResponse(BaseModel):
    """单个 C# 文件迁移结果。"""

    success: bool
    file_name: str
    output_file: str
    ts_info: dict[str, Any] | None = None
    error: str | None = None


class BatchCsMigrationRequest(BaseModel):
    """项目级 C# 文件迁移请求。"""

    project_name: str
    cs_dependency_file: str
    output_dir: str
    ts_info_file: str


class BatchCsMigrationResponse(BaseModel):
    """项目级 C# 文件迁移结果。"""

    success: bool
    message: str
    files_migrated: int
    files_failed: int
    migrated_files: list[str]
    failed_files: list[str]
    output_dir: str


class DataMigrationRequest(BaseModel):
    """项目级数据资源迁移请求。"""

    project_name: str
    data_resources_file: str
    output_file: str


class DataMigrationResponse(BaseModel):
    """项目级数据资源迁移结果。"""

    success: bool
    message: str
    data_resources_migrated: int
    data_resources_failed: int
    migrated_keys: list[str]
    failed_keys: list[str]
    output_file: str
