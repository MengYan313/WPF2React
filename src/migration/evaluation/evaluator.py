"""组件、页面和页面调用三层评测编排及结果持久化。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from src.common.logging import get_logger

from .matcher import ComponentJudge, DeterministicComponentJudge
from .models import (
    CallEvaluationResult,
    CallEvaluationStatus,
    CompileStatus,
    ComponentEvaluationResult,
    ComponentEvaluationStatus,
    EvaluationManifest,
    EvaluationReport,
    EvaluationSummary,
    MatchStatus,
    PageEvaluationResult,
    PageEvaluationStatus,
)
from .runner import CallTestRunner, TypeScriptCompileRunner


logger = get_logger(__name__)


class MigrationEvaluator:
    """只读评测迁移结果，不修改或修复目标代码。"""

    def __init__(
        self,
        manifest: EvaluationManifest,
        *,
        workspace_root: str | Path = ".",
        judge: ComponentJudge | None = None,
    ) -> None:
        self.manifest = manifest
        self.workspace_root = Path(workspace_root).resolve()
        self.target_root = self._resolve_workspace_path(manifest.target_root)
        self.judge = judge or DeterministicComponentJudge()
        self.compiler = TypeScriptCompileRunner(
            self.target_root,
            manifest.compiler,
        )
        self.call_tester = CallTestRunner(
            self.target_root,
            manifest.call_tester,
        )

    def evaluate(self, *, method_id: str, run_id: str) -> EvaluationReport:
        logger.info(
            "开始迁移评测: project=%s, method=%s, run=%s",
            self.manifest.project_id,
            method_id,
            run_id,
        )
        component_results = self._evaluate_components()
        page_results = self._evaluate_pages()
        call_results = self._evaluate_calls(page_results)
        summary = self._summarize(
            component_results,
            page_results,
            call_results,
        )
        logger.info(
            "评测完成: C-CPR=%s, P-CPR=%s, PECTPR=%s",
            self._format_metric(summary.c_cpr),
            self._format_metric(summary.p_cpr),
            self._format_metric(summary.pectpr),
        )
        return EvaluationReport(
            project_id=self.manifest.project_id,
            method_id=method_id,
            run_id=run_id,
            target_root=str(self.target_root),
            component_results=component_results,
            page_results=page_results,
            call_results=call_results,
            summary=summary,
        )

    def _evaluate_components(self) -> list[ComponentEvaluationResult]:
        matches = self.judge.judge(self.manifest.components, self.target_root)
        if len(matches) != len(self.manifest.components):
            raise ValueError("组件判别器返回数量与输入组件数量不一致")

        results: list[ComponentEvaluationResult] = []
        for component, match in zip(self.manifest.components, matches):
            if match.component_id != component.component_id:
                raise ValueError("组件判别器返回顺序或 component_id 不符合契约")
            if match.status == MatchStatus.NOT_FOUND:
                status = ComponentEvaluationStatus.NOT_FOUND
                compile_result = None
            elif match.status == MatchStatus.AMBIGUOUS:
                status = ComponentEvaluationStatus.AMBIGUOUS
                compile_result = None
            elif match.status == MatchStatus.EVALUATOR_ERROR:
                status = ComponentEvaluationStatus.EVALUATOR_ERROR
                compile_result = None
            elif not match.target_file:
                status = ComponentEvaluationStatus.EVALUATOR_ERROR
                compile_result = None
                match.evidence.append("MATCHED 结果缺少 target_file")
            else:
                compile_result = self.compiler.compile(
                    self.target_root / match.target_file
                )
                status = self._component_status_from_compile(compile_result.status)
            results.append(
                ComponentEvaluationResult(
                    component_id=component.component_id,
                    page_id=component.page_id,
                    status=status,
                    match=match,
                    compile_result=compile_result,
                )
            )
        return results

    def _evaluate_pages(self) -> list[PageEvaluationResult]:
        results: list[PageEvaluationResult] = []
        for page in self.manifest.pages:
            candidates = []
            for hint in page.target_file_hints:
                candidate = (self.target_root / hint).resolve()
                try:
                    candidate.relative_to(self.target_root)
                except ValueError:
                    continue
                if candidate.is_file() and candidate not in candidates:
                    candidates.append(candidate)

            if not candidates:
                results.append(
                    PageEvaluationResult(
                        page_id=page.page_id,
                        status=PageEvaluationStatus.PAGE_MISSING,
                        evidence=["未找到页面目标文件"],
                    )
                )
                continue
            if len(candidates) > 1:
                results.append(
                    PageEvaluationResult(
                        page_id=page.page_id,
                        status=PageEvaluationStatus.PAGE_AMBIGUOUS,
                        evidence=[
                            "多个目标文件符合页面提示: "
                            + ", ".join(
                                str(path.relative_to(self.target_root))
                                for path in candidates
                            )
                        ],
                    )
                )
                continue

            target_file = candidates[0]
            compile_result = self.compiler.compile(target_file)
            results.append(
                PageEvaluationResult(
                    page_id=page.page_id,
                    status=self._page_status_from_compile(compile_result.status),
                    target_file=str(target_file.relative_to(self.target_root)),
                    compile_result=compile_result,
                    evidence=["页面文件通过 manifest 的仓库相对精确路径定位"],
                )
            )
        return results

    def _evaluate_calls(
        self,
        page_results: list[PageEvaluationResult],
    ) -> list[CallEvaluationResult]:
        page_statuses = {result.page_id: result.status for result in page_results}
        results: list[CallEvaluationResult] = []
        for edge in self.manifest.call_edges:
            if not self.call_tester.is_configured(edge):
                results.append(self.call_tester.run(edge))
                continue
            unavailable = [
                page_id
                for page_id in (edge.source_page, edge.target_page)
                if page_statuses.get(page_id)
                != PageEvaluationStatus.PAGE_COMPILE_PASSED
            ]
            if unavailable:
                if any(
                    page_statuses.get(page_id) == PageEvaluationStatus.EVALUATOR_ERROR
                    for page_id in unavailable
                ):
                    status = CallEvaluationStatus.EVALUATOR_ERROR
                    error = "关联页面发生评测器错误: " + ", ".join(unavailable)
                else:
                    status = CallEvaluationStatus.PAGE_UNAVAILABLE
                    error = "关联页面未通过编译: " + ", ".join(unavailable)
                results.append(
                    CallEvaluationResult(
                        edge_id=edge.edge_id,
                        source_page=edge.source_page,
                        target_page=edge.target_page,
                        status=status,
                        error=error,
                    )
                )
                continue
            results.append(self.call_tester.run(edge))
        return results

    def _resolve_workspace_path(self, value: str) -> Path:
        path = Path(value)
        return path.resolve() if path.is_absolute() else (self.workspace_root / path).resolve()

    @staticmethod
    def _component_status_from_compile(
        status: CompileStatus,
    ) -> ComponentEvaluationStatus:
        if status == CompileStatus.PASSED:
            return ComponentEvaluationStatus.COMPILE_PASSED
        if status == CompileStatus.FAILED:
            return ComponentEvaluationStatus.COMPILE_FAILED
        return ComponentEvaluationStatus.EVALUATOR_ERROR

    @staticmethod
    def _page_status_from_compile(status: CompileStatus) -> PageEvaluationStatus:
        if status == CompileStatus.PASSED:
            return PageEvaluationStatus.PAGE_COMPILE_PASSED
        if status == CompileStatus.FAILED:
            return PageEvaluationStatus.PAGE_COMPILE_FAILED
        return PageEvaluationStatus.EVALUATOR_ERROR

    @staticmethod
    def _format_metric(value: float | None) -> str:
        return "不可用" if value is None else f"{value:.4f}"

    @classmethod
    def _summarize(
        cls,
        component_results: list[ComponentEvaluationResult],
        page_results: list[PageEvaluationResult],
        call_results: list[CallEvaluationResult],
    ) -> EvaluationSummary:
        component_counts = cls._count_statuses(component_results)
        page_counts = cls._count_statuses(page_results)
        call_counts = cls._count_statuses(call_results)

        component_total = len(component_results)
        component_errors = component_counts.get(
            ComponentEvaluationStatus.EVALUATOR_ERROR, 0
        )
        component_passed = component_counts.get(
            ComponentEvaluationStatus.COMPILE_PASSED, 0
        )
        component_missing = (
            component_counts.get(ComponentEvaluationStatus.NOT_FOUND, 0)
            + component_counts.get(ComponentEvaluationStatus.AMBIGUOUS, 0)
        )
        component_failed = component_counts.get(
            ComponentEvaluationStatus.COMPILE_FAILED, 0
        )

        page_total = len(page_results)
        page_errors = page_counts.get(PageEvaluationStatus.EVALUATOR_ERROR, 0)
        page_passed = page_counts.get(
            PageEvaluationStatus.PAGE_COMPILE_PASSED, 0
        )
        page_missing = (
            page_counts.get(PageEvaluationStatus.PAGE_MISSING, 0)
            + page_counts.get(PageEvaluationStatus.PAGE_AMBIGUOUS, 0)
        )
        page_failed = page_counts.get(
            PageEvaluationStatus.PAGE_COMPILE_FAILED, 0
        )

        call_total = len(call_results)
        call_passed = call_counts.get(CallEvaluationStatus.TEST_PASSED, 0)
        call_failed = call_counts.get(CallEvaluationStatus.TEST_FAILED, 0)
        call_unavailable = call_counts.get(CallEvaluationStatus.PAGE_UNAVAILABLE, 0)
        call_not_configured = call_counts.get(
            CallEvaluationStatus.TEST_NOT_CONFIGURED, 0
        )
        call_errors = call_counts.get(CallEvaluationStatus.EVALUATOR_ERROR, 0)
        configured_calls = call_total - call_not_configured

        component_metrics_valid = component_errors == 0
        page_metrics_valid = page_errors == 0
        call_metrics_valid = call_not_configured == 0 and call_errors == 0

        return EvaluationSummary(
            component_total=component_total,
            component_compile_passed=component_passed,
            component_missing_or_ambiguous=component_missing,
            component_compile_failed=component_failed,
            component_evaluator_errors=component_errors,
            c_cpr=cls._ratio(component_passed, component_total, component_metrics_valid),
            c_mr=cls._ratio(component_missing, component_total, component_metrics_valid),
            c_cfr=cls._ratio(component_failed, component_total, component_metrics_valid),
            page_total=page_total,
            page_compile_passed=page_passed,
            page_missing_or_ambiguous=page_missing,
            page_compile_failed=page_failed,
            page_evaluator_errors=page_errors,
            p_cpr=cls._ratio(page_passed, page_total, page_metrics_valid),
            call_edge_total=call_total,
            call_test_passed=call_passed,
            call_test_failed=call_failed,
            call_page_unavailable=call_unavailable,
            call_not_configured=call_not_configured,
            call_evaluator_errors=call_errors,
            call_test_coverage=cls._ratio(configured_calls, call_total, True),
            pectpr=cls._ratio(call_passed, call_total, call_metrics_valid),
        )

    @staticmethod
    def _ratio(numerator: int, denominator: int, valid: bool) -> float | None:
        if not valid or denominator == 0:
            return None
        return numerator / denominator

    @staticmethod
    def _count_statuses(results: Iterable[object]) -> dict[object, int]:
        counts: dict[object, int] = {}
        for result in results:
            status = getattr(result, "status")
            counts[status] = counts.get(status, 0) + 1
        return counts


def write_evaluation_outputs(
    report: EvaluationReport,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """写入完整 JSON 报告和逐项 JSONL 证据。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "evaluation_report.json"
    records_path = output_dir / "evaluation_records.jsonl"

    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    common = {
        "schema_version": report.schema_version,
        "project_id": report.project_id,
        "method_id": report.method_id,
        "run_id": report.run_id,
    }
    records: list[dict[str, object]] = []
    for unit_type, results in (
        ("component", report.component_results),
        ("page", report.page_results),
        ("call_edge", report.call_results),
    ):
        for result in results:
            records.append(
                {
                    **common,
                    "unit_type": unit_type,
                    "result": result.model_dump(mode="json"),
                }
            )
    records_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False) + "\n" for record in records
        ),
        encoding="utf-8",
    )
    return report_path, records_path
