"""MigraUI-NoRAG 单控件页面的真实 LLM 端到端 smoke。"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration.baselines.common import METHOD_NO_RAG, BaselineRunPaths
from src.migration.baselines.no_rag import MigraUINoRAGRunner

from .test_page_pipeline_smoke import (
    SYNTHETIC_CONTROL_DATA,
    SYNTHETIC_PAGE_DEPENDENCY,
)


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.json_mode_config()
    with tempfile.TemporaryDirectory(prefix="wpf2react-no-rag-baseline-") as temp_dir:
        workspace = Path(temp_dir)
        project_id = "SyntheticSmoke"
        source_root = workspace / "repos" / project_id
        source_root.mkdir(parents=True)
        (source_root / "SmokePage.xaml").write_text(
            SYNTHETIC_CONTROL_DATA["root_info"]["source_code"],
            encoding="utf-8",
        )
        dependency_dir = workspace / "parser-outputs" / project_id / "dependency"
        dependency_dir.mkdir(parents=True)
        control_file = dependency_dir / "controls" / "SmokePage.xaml.json"
        control_file.parent.mkdir(parents=True)
        control_file.write_text(
            json.dumps(SYNTHETIC_CONTROL_DATA, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (dependency_dir / "page_dependency.json").write_text(
            json.dumps(SYNTHETIC_PAGE_DEPENDENCY, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths = BaselineRunPaths.build(
            METHOD_NO_RAG,
            "smoke",
            project_id,
            source_base_dir=workspace / "repos",
            result_base_dir=workspace / "results" / "baselines",
            artifact_base_dir=workspace / "outputs" / "baselines",
        )
        summary = await MigraUINoRAGRunner(
            paths,
            parser_output_base_dir=str(workspace / "parser-outputs"),
            llm_config=config,
        ).run(page_names=["SmokePage.xaml"], run_project_stages=False)
        output = paths.result_root / "SmokePage.tsx"
        content = output.read_text(encoding="utf-8") if output.is_file() else ""
        usage = summary.get("llm_usage") or {}
        success = (
            summary.get("status") == "success"
            and summary.get("mui_retrieval_enabled") is False
            and summary.get("mui_document_injection_enabled") is False
            and summary.get("component_split_enabled") is True
            and usage.get("provider_calls", 0) > 0
            and usage.get("total_tokens", 0) > 0
            and bool(content)
            and "<Grid" not in content
        )
        print(f"model={config.model}")
        print(f"status={summary.get('status')}")
        print(f"retrieval_enabled={summary.get('mui_retrieval_enabled')}")
        print(f"provider_calls={usage.get('provider_calls')}")
        print(f"total_tokens={usage.get('total_tokens')}")
        print(f"output_nonempty={bool(content)}")
        print(f"grid_absent={'<Grid' not in content}")
        return success


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
