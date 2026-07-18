"""三条 baseline 的统一程序化入口。"""

from __future__ import annotations

from typing import Any, Sequence

from src.llm import LLMConfig

from .common import (
    METHOD_LLM_DIRECT,
    METHOD_NO_RAG,
    METHOD_RULETRANS,
    BaselineRunPaths,
)
from .llm_direct import LLMDirectBudgetRunner
from .no_rag import MigraUINoRAGRunner
from .ruletrans import RuleTransMUIRunner


async def run_baseline(
    method_id: str,
    project_id: str,
    run_id: str,
    *,
    source_base_dir: str = "repos",
    result_base_dir: str = "results/baselines",
    artifact_base_dir: str = "outputs/baselines",
    parser_output_base_dir: str = "outputs",
    page_names: Sequence[str] | None = None,
    merge_project: bool = True,
    run_project_stages: bool = True,
    total_token_budget: int = 120_000,
    max_input_tokens_per_call: int = 24_000,
    max_output_tokens_per_call: int = 8_000,
    llm_config: LLMConfig | None = None,
) -> dict[str, Any]:
    paths = BaselineRunPaths.build(
        method_id,
        run_id,
        project_id,
        source_base_dir=source_base_dir,
        result_base_dir=result_base_dir,
        artifact_base_dir=artifact_base_dir,
    )
    if method_id == METHOD_RULETRANS:
        return RuleTransMUIRunner(paths).run()
    if method_id == METHOD_LLM_DIRECT:
        return await LLMDirectBudgetRunner(
            paths,
            llm_config=llm_config,
            total_token_budget=total_token_budget,
            max_input_tokens_per_call=max_input_tokens_per_call,
            max_output_tokens_per_call=max_output_tokens_per_call,
        ).run(page_names=page_names, merge_project=merge_project)
    if method_id == METHOD_NO_RAG:
        return await MigraUINoRAGRunner(
            paths,
            parser_output_base_dir=parser_output_base_dir,
            llm_config=llm_config,
        ).run(page_names=page_names, run_project_stages=run_project_stages)
    raise ValueError(f"未知 baseline: {method_id}")
