"""MigraUI-NoRAG：仅关闭 MUI 知识检索的完整流程消融基线。"""

from __future__ import annotations

import time
from typing import Any, Sequence

from src.common.logging import get_logger
from src.llm import LLMConfig
from src.migration.migration_orchestrator import MigrationOrchestrator

from .common import (
    METHOD_NO_RAG,
    BaselineRunPaths,
    copy_binary_assets,
    copy_parser_outputs,
    create_target_skeleton,
    utc_now,
    write_json,
)


class MigraUINoRAGRunner:
    """复用 MigraUI 编排，仅禁止知识库查询和 MUI 文档注入。"""

    def __init__(
        self,
        paths: BaselineRunPaths,
        *,
        parser_output_base_dir: str = "outputs",
        llm_config: LLMConfig | None = None,
    ) -> None:
        if paths.method_id != METHOD_NO_RAG:
            raise ValueError("MigraUINoRAGRunner 只接受 MigraUI-NoRAG 路径")
        self.paths = paths
        self.parser_output_base_dir = parser_output_base_dir
        self.llm_config = llm_config
        self.logger = get_logger(__name__)

    async def run(
        self,
        *,
        page_names: Sequence[str] | None = None,
        run_project_stages: bool = True,
    ) -> dict[str, Any]:
        started_at = utc_now()
        started = time.perf_counter()
        self.paths.prepare()
        skeleton_files = create_target_skeleton(self.paths.result_root)
        assets = copy_binary_assets(self.paths.source_root, self.paths.result_root)
        isolated_parser_base = copy_parser_outputs(
            self.paths.project_id,
            self.paths.artifact_root,
            parser_output_base_dir=self.parser_output_base_dir,
        )
        config = self.llm_config or LLMConfig.json_mode_config()
        orchestrator = MigrationOrchestrator(
            project_name=self.paths.project_id,
            output_base_dir=str(isolated_parser_base),
            result_dir=str(self.paths.result_root),
            enable_mui_retrieval=False,
            llm_config=config,
        )
        migration_summary = await orchestrator.orchestrate_migration(
            page_names=list(page_names) if page_names is not None else None,
            run_project_stages=run_project_stages,
        )
        llm_usage = orchestrator.migration_team.get_llm_usage()
        write_json(
            self.paths.artifact_root / "migration_summary.json",
            migration_summary,
        )
        summary = {
            "method_id": METHOD_NO_RAG,
            "run_id": self.paths.run_id,
            "project_id": self.paths.project_id,
            "status": (
                "success"
                if migration_summary.get("total_pages", 0) > 0
                and migration_summary.get("failed_pages", 0) == 0
                else "failed"
            ),
            "started_at": started_at,
            "finished_at": utc_now(),
            "wall_time_seconds": round(time.perf_counter() - started, 6),
            "source_root": str(self.paths.source_root),
            "result_root": str(self.paths.result_root),
            "artifact_root": str(self.paths.artifact_root),
            "isolated_parser_output_base": str(isolated_parser_base),
            "model": config.model,
            "mui_retrieval_enabled": False,
            "standard_mapping_enabled": True,
            "mui_document_injection_enabled": False,
            "component_split_enabled": True,
            "bottom_up_enabled": True,
            "child_code_injection_enabled": True,
            "dependency_schedule_enabled": True,
            "repair_enabled": True,
            "run_project_stages": run_project_stages,
            "page_filter": list(page_names) if page_names is not None else None,
            "total_pages": migration_summary.get("total_pages", 0),
            "successful_pages": migration_summary.get("successful_pages", 0),
            "failed_pages": migration_summary.get("failed_pages", 0),
            "llm_usage": llm_usage,
            "llm_usage_source": "AutoGen model_client.actual_usage",
            "skeleton_files": skeleton_files,
            "binary_assets": assets,
        }
        write_json(self.paths.artifact_root / "run_manifest.json", summary)
        self.logger.info(
            "MigraUI-NoRAG 完成: %s/%s 页面",
            summary["successful_pages"],
            summary["total_pages"],
        )
        return summary
