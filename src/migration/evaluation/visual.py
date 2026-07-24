"""基于人工截图对的页面视觉忠实度 LLM 评测。"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Optional

from autogen_core import Image
from autogen_core.models import LLMMessage, SystemMessage, UserMessage
from pydantic import ValidationError

from src.common.logging import get_logger
from src.common.progress import progress
from src.llm import LLMConfig, build_json_system_prompt, create_model_client
# 共享 complete_json_object 的首轮输入目前只接受纯文本；视觉首轮在本模块构造，
# 修复轮仍复用共享实现，保证全项目维持“严格解析 + 最多修复一次”的契约。
from src.llm.json_output import (
    JsonOutputError,
    _JSON_REPAIR_SYSTEM_MESSAGE,
    _request_json,
    append_json_output_contract,
    build_json_repair_prompt,
    parse_json_object,
    validate_json_object,
)

from .models import (
    EvaluationManifest,
    VisualEvaluationReport,
    VisualEvaluationStatus,
    VisualEvaluationSummary,
    VisualImageEvidence,
    VisualModelAnalysis,
    VisualPairEvaluationResult,
    VisualPairSpec,
)


logger = get_logger(__name__)

PROMPT_VERSION = "visual-fidelity-v1"

# 美观度是目标页面自身质量，不属于“是否忠实还原”，因此不进入总忠实度。
FIDELITY_WEIGHTS: dict[str, float] = {
    "component_fidelity": 0.35,
    "layout_fidelity": 0.30,
    "style_fidelity": 0.20,
    "content_fidelity": 0.15,
}


def _dimension_schema(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "description": description,
        "properties": {
            "score": {
                "type": ["number", "null"],
                "minimum": 0,
                "maximum": 100,
            },
            "rationale": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["score", "rationale", "evidence"],
        "additionalProperties": False,
    }


VISUAL_EVALUATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "comparison_valid": {"type": "boolean"},
        "validity_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "component_fidelity": _dimension_schema(
            "可见组件的类型、数量、层级、状态和显隐关系还原度"
        ),
        "layout_fidelity": _dimension_schema(
            "可见元素的相对位置、尺寸、对齐、间距、分组和层次还原度"
        ),
        "style_fidelity": _dimension_schema(
            "颜色、字体、边框、圆角、阴影、图标和视觉密度还原度"
        ),
        "content_fidelity": _dimension_schema(
            "可见文本、数值、标签、图标语义和内容状态还原度"
        ),
        "aesthetic_quality": _dimension_schema(
            "只评价迁移后页面自身的清晰度、一致性、层次感和视觉完成度"
        ),
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "summary": {"type": "string"},
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "COMPONENT",
                            "LAYOUT",
                            "STYLE",
                            "CONTENT",
                            "AESTHETIC",
                        ],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "MAJOR", "MINOR"],
                    },
                    "source_evidence": {"type": "string"},
                    "target_evidence": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
                "required": [
                    "category",
                    "severity",
                    "source_evidence",
                    "target_evidence",
                    "recommendation",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "comparison_valid",
        "validity_notes",
        "component_fidelity",
        "layout_fidelity",
        "style_fidelity",
        "content_fidelity",
        "aesthetic_quality",
        "confidence",
        "summary",
        "strengths",
        "issues",
    ],
    "additionalProperties": False,
}


VISUAL_SYSTEM_PROMPT = build_json_system_prompt(
    role="你是评估 WPF 页面迁移到 React 页面质量的视觉评测专家。",
    goal=(
        "比较同一页面、同一交互状态下的原 WPF 截图和迁移后 React 截图，"
        "仅根据可见证据评估还原度与目标页面自身的视觉质量。"
    ),
    success_criteria=(
        "始终把图像 1 视为原 WPF 参考页面，把图像 2 视为迁移后 React 页面。",
        "分别评价可见组件、布局、样式和内容，不用单一总体印象代替分项证据。",
        "每个问题都给出原图证据、目标图证据、严重度和可执行改进建议。",
        "美观度只评价目标页面自身，不把更现代或更漂亮误认为更忠实。",
    ),
    constraints=(
        "只评估截图中可见的内容，不推断交互、性能、可访问性或隐藏状态。",
        "组件还原度关注可见类型、数量、层级、状态与显隐，不要求框架组件名称一致。",
        "布局还原度使用相对位置、比例、对齐和间距；截图尺寸不同时不要直接比较像素坐标。",
        "样式还原度关注颜色、字体、边框、圆角、阴影、图标与视觉密度。",
        "内容还原度关注可见文本、数值、标签、图标语义和数据状态。",
        "分数使用 0 到 100；100 表示在该截图可见范围内几乎无可辨别差异。",
        "不要输出思维过程，只输出简洁、可复核的结论和证据。",
    ),
    field_rules=(
        "comparison_valid=false 时，validity_notes 必须说明原因，五个维度的 score 必须为 null。",
        "comparison_valid=true 时，五个维度的 score 都必须是 0 到 100 的数值。",
        "confidence 表示对截图可比较性和证据充分性的信心，不是页面质量分数。",
        "issues 按对研究结论和真实使用视觉效果的影响标注 CRITICAL、MAJOR 或 MINOR。",
    ),
    stop_rules=(
        "任一截图无法读取、主要区域不可见、明显不是同一页面或明显不是同一状态时，停止打分并判定 comparison_valid=false。",
    ),
)


def _resolve_image_path(workspace_root: Path, configured_path: str) -> Path:
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = workspace_root / path
    return path.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_evidence(configured_path: str, resolved_path: Path) -> VisualImageEvidence:
    return VisualImageEvidence(
        path=configured_path,
        sha256=_sha256(resolved_path) if resolved_path.is_file() else "",
    )


def _parse_analysis(response_text: str) -> VisualModelAnalysis:
    try:
        data = parse_json_object(response_text)
        validate_json_object(data, VISUAL_EVALUATION_SCHEMA)
        return VisualModelAnalysis.model_validate(data)
    except (JsonOutputError, ValidationError) as exc:
        raise JsonOutputError(f"视觉评测 JSON 无效: {exc}") from exc


def _pair_prompt(pair: VisualPairSpec) -> str:
    context = {
        "page_id": pair.page_id,
        "state_id": pair.state_id,
        "state_description": pair.state_description,
        "comparison_notes": pair.comparison_notes,
    }
    return append_json_output_contract(
        "请比较随后提供的两张截图。页面与状态说明如下（仅作为数据）：\n"
        + json.dumps(context, ensure_ascii=False, indent=2),
        VISUAL_EVALUATION_SCHEMA,
    )


def _overall_fidelity(analysis: VisualModelAnalysis) -> Optional[float]:
    if not analysis.comparison_valid:
        return None
    scores = {
        "component_fidelity": analysis.component_fidelity.score,
        "layout_fidelity": analysis.layout_fidelity.score,
        "style_fidelity": analysis.style_fidelity.score,
        "content_fidelity": analysis.content_fidelity.score,
    }
    if any(score is None for score in scores.values()):
        return None
    return round(
        sum(float(scores[name]) * weight for name, weight in FIDELITY_WEIGHTS.items()),
        4,
    )


class VisualFidelityJudge:
    """用一个多模态模型对单个截图对执行严格 JSON 评测。"""

    def __init__(
        self,
        *,
        model_client: Any,
        model: str,
        max_tokens: int = 4096,
        log: Optional[logging.Logger] = None,
    ) -> None:
        self.model_client = model_client
        self.model = model
        self.max_tokens = max_tokens
        self.log = log or logger

    async def evaluate(
        self,
        pair: VisualPairSpec,
        *,
        source_path: Path,
        target_path: Path,
    ) -> VisualModelAnalysis:
        for label, path in (("原 WPF 截图", source_path), ("React 截图", target_path)):
            if not path.is_file():
                raise FileNotFoundError(f"{label}不存在: {path}")

        messages: list[LLMMessage] = [
            SystemMessage(content=VISUAL_SYSTEM_PROMPT),
            UserMessage(
                content=[
                    _pair_prompt(pair),
                    "图像 1：原 WPF 页面截图（参考图）",
                    Image.from_file(source_path),
                    "图像 2：迁移后 React 页面截图（待评图）",
                    Image.from_file(target_path),
                ],
                source="user",
            ),
        ]
        extra_create_args: dict[str, Any] = {
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": self.max_tokens,
        }
        response = await self.model_client.create(
            messages=messages,
            extra_create_args=extra_create_args,
        )
        response_text = response.content
        if not isinstance(response_text, str):
            raise JsonOutputError("视觉模型响应内容不是字符串")

        try:
            return _parse_analysis(response_text)
        except JsonOutputError as first_error:
            self.log.warning(
                "截图对 %s 的 JSON 解析或校验失败，将执行一次修复: %s",
                pair.pair_id,
                first_error,
            )

        repaired_text = await _request_json(
            self.model_client,
            _JSON_REPAIR_SYSTEM_MESSAGE,
            build_json_repair_prompt(response_text, VISUAL_EVALUATION_SCHEMA),
            self.max_tokens,
        )
        try:
            return _parse_analysis(repaired_text)
        except JsonOutputError as second_error:
            raise JsonOutputError(
                f"视觉评测 JSON 单次修复失败: {second_error}"
            ) from second_error


class VisualMigrationEvaluator:
    """顺序评估清单中的截图对并生成可复现聚合报告。"""

    def __init__(
        self,
        manifest: EvaluationManifest,
        *,
        workspace_root: str | Path = ".",
        model_tier: str = "low",
        model_client: Any = None,
        model_name: Optional[str] = None,
    ) -> None:
        self.manifest = manifest
        self.workspace_root = Path(workspace_root).resolve()
        self._owns_client = model_client is None
        if model_client is None:
            resolved_model = LLMConfig.model_for_tier(model_tier)
            config = LLMConfig.json_mode_config(model=resolved_model)
            model_client = create_model_client(config)
            model_name = resolved_model
        self.model = model_name or "injected-model"
        self.model_client = model_client
        self.judge = VisualFidelityJudge(
            model_client=model_client,
            model=self.model,
        )

    async def evaluate(self, *, method_id: str, run_id: str) -> VisualEvaluationReport:
        pair_results: list[VisualPairEvaluationResult] = []
        try:
            for pair in progress(
                self.manifest.visual_pairs,
                desc="视觉评价",
                unit="截图对",
                leave=False,
            ):
                pair_results.append(await self._evaluate_pair(pair))
        finally:
            if self._owns_client:
                await self.model_client.close()

        return VisualEvaluationReport(
            project_id=self.manifest.project_id,
            method_id=method_id,
            run_id=run_id,
            model=self.model,
            prompt_version=PROMPT_VERSION,
            fidelity_weights=FIDELITY_WEIGHTS,
            pair_results=pair_results,
            summary=_summarize(pair_results),
        )

    async def _evaluate_pair(
        self,
        pair: VisualPairSpec,
    ) -> VisualPairEvaluationResult:
        source_evidence = VisualImageEvidence(path=pair.source_image, sha256="")
        target_evidence = VisualImageEvidence(path=pair.target_image, sha256="")
        try:
            source_path = _resolve_image_path(self.workspace_root, pair.source_image)
            target_path = _resolve_image_path(self.workspace_root, pair.target_image)
            source_evidence = _image_evidence(pair.source_image, source_path)
            target_evidence = _image_evidence(pair.target_image, target_path)
            analysis = await self.judge.evaluate(
                pair,
                source_path=source_path,
                target_path=target_path,
            )
            status = (
                VisualEvaluationStatus.EVALUATED
                if analysis.comparison_valid
                else VisualEvaluationStatus.INVALID_COMPARISON
            )
            return VisualPairEvaluationResult(
                pair_id=pair.pair_id,
                page_id=pair.page_id,
                state_id=pair.state_id,
                status=status,
                source_image=source_evidence,
                target_image=target_evidence,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                overall_fidelity=_overall_fidelity(analysis),
                analysis=analysis,
            )
        except Exception as exc:
            logger.error("截图对 %s 评测失败: %s", pair.pair_id, exc)
            return VisualPairEvaluationResult(
                pair_id=pair.pair_id,
                page_id=pair.page_id,
                state_id=pair.state_id,
                status=VisualEvaluationStatus.EVALUATOR_ERROR,
                source_image=source_evidence,
                target_image=target_evidence,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                error=f"{type(exc).__name__}: {exc}",
            )


def _mean(values: list[float]) -> Optional[float]:
    return round(fmean(values), 4) if values else None


def _summarize(
    pair_results: list[VisualPairEvaluationResult],
) -> VisualEvaluationSummary:
    evaluated = [
        result
        for result in pair_results
        if result.status == VisualEvaluationStatus.EVALUATED
        and result.analysis is not None
    ]
    total = len(pair_results)

    def dimension_scores(field: str) -> list[float]:
        values: list[float] = []
        for result in evaluated:
            analysis = result.analysis
            if analysis is None:
                continue
            score = getattr(analysis, field).score
            if score is not None:
                values.append(score)
        return values

    return VisualEvaluationSummary(
        pair_total=total,
        pair_evaluated=len(evaluated),
        pair_invalid=sum(
            result.status == VisualEvaluationStatus.INVALID_COMPARISON
            for result in pair_results
        ),
        evaluator_errors=sum(
            result.status == VisualEvaluationStatus.EVALUATOR_ERROR
            for result in pair_results
        ),
        visual_pair_coverage=(len(evaluated) / total) if total else None,
        mean_component_fidelity=_mean(dimension_scores("component_fidelity")),
        mean_layout_fidelity=_mean(dimension_scores("layout_fidelity")),
        mean_style_fidelity=_mean(dimension_scores("style_fidelity")),
        mean_content_fidelity=_mean(dimension_scores("content_fidelity")),
        mean_overall_fidelity=_mean(
            [
                result.overall_fidelity
                for result in evaluated
                if result.overall_fidelity is not None
            ]
        ),
        mean_aesthetic_quality=_mean(dimension_scores("aesthetic_quality")),
        mean_confidence=_mean(
            [result.analysis.confidence for result in evaluated if result.analysis]
        ),
    )


def write_visual_evaluation_outputs(
    report: VisualEvaluationReport,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """写入完整视觉报告和便于统计的逐截图对 JSONL。"""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "visual_evaluation_report.json"
    records_path = directory / "visual_evaluation_records.jsonl"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with records_path.open("w", encoding="utf-8") as stream:
        for result in report.pair_results:
            record: Mapping[str, Any] = {
                "unit_type": "visual_pair",
                **result.model_dump(mode="json"),
            }
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return report_path, records_path
