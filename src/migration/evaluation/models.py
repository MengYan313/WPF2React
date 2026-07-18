"""评测清单、逐项结果和汇总指标的数据契约。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class CommandSpec(BaseModel):
    """不经过 shell 执行的命令模板。"""

    command: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=120, ge=1)


class ComponentSpec(BaseModel):
    """由源侧确定性规则抽取的组件实例。"""

    component_id: str
    page_id: str
    source_file: str
    source_node_path: str
    source_tag: str
    source_name: Optional[str] = None
    source_attributes: dict[str, str] = Field(default_factory=dict)
    target_file_hints: list[str] = Field(default_factory=list)
    target_symbol_hints: list[str] = Field(default_factory=list)
    target_tag_hints: list[str] = Field(default_factory=list)
    text_hints: list[str] = Field(default_factory=list)


class PageSpec(BaseModel):
    """源页面及目标入口候选。"""

    page_id: str
    source_file: str
    target_file_hints: list[str] = Field(default_factory=list)


class CallEdgeSpec(BaseModel):
    """页面调用关系 GT 及其可执行测试入口。"""

    edge_id: str
    source_page: str
    target_page: str
    call_type: str = "page_dependency"
    test_file: Optional[str] = None
    test_command: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualPairSpec(BaseModel):
    """人工提供的同一页面、同一状态的迁移前后截图对。"""

    pair_id: str
    page_id: str
    source_image: str
    target_image: str
    state_id: str = "default"
    state_description: Optional[str] = None
    comparison_notes: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationManifest(BaseModel):
    """与迁移方法隔离、冻结后供评测器读取的清单。"""

    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    target_root: str
    components: list[ComponentSpec] = Field(default_factory=list)
    pages: list[PageSpec] = Field(default_factory=list)
    call_edges: list[CallEdgeSpec] = Field(default_factory=list)
    visual_pairs: list[VisualPairSpec] = Field(default_factory=list)
    compiler: CommandSpec = Field(default_factory=CommandSpec)
    call_tester: CommandSpec = Field(default_factory=CommandSpec)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "EvaluationManifest":
        page_ids = [page.page_id for page in self.pages]
        component_ids = [component.component_id for component in self.components]
        edge_ids = [edge.edge_id for edge in self.call_edges]
        pair_ids = [pair.pair_id for pair in self.visual_pairs]

        for label, values in (
            ("page_id", page_ids),
            ("component_id", component_ids),
            ("edge_id", edge_ids),
            ("pair_id", pair_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"评测清单包含重复的 {label}")

        known_pages = set(page_ids)
        for component in self.components:
            if component.page_id not in known_pages:
                raise ValueError(
                    f"组件 {component.component_id} 引用了未知页面 {component.page_id}"
                )
        for edge in self.call_edges:
            if edge.source_page not in known_pages or edge.target_page not in known_pages:
                raise ValueError(f"调用边 {edge.edge_id} 引用了未知页面")
        for pair in self.visual_pairs:
            if pair.page_id not in known_pages:
                raise ValueError(f"截图对 {pair.pair_id} 引用了未知页面 {pair.page_id}")
        return self


class MatchStatus(str, Enum):
    MATCHED = "MATCHED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    EVALUATOR_ERROR = "EVALUATOR_ERROR"


class CompileStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    EVALUATOR_ERROR = "EVALUATOR_ERROR"
    NOT_RUN = "NOT_RUN"


class ComponentEvaluationStatus(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    COMPILE_FAILED = "COMPILE_FAILED"
    COMPILE_PASSED = "COMPILE_PASSED"
    EVALUATOR_ERROR = "EVALUATOR_ERROR"


class PageEvaluationStatus(str, Enum):
    PAGE_MISSING = "PAGE_MISSING"
    PAGE_AMBIGUOUS = "PAGE_AMBIGUOUS"
    PAGE_COMPILE_FAILED = "PAGE_COMPILE_FAILED"
    PAGE_COMPILE_PASSED = "PAGE_COMPILE_PASSED"
    EVALUATOR_ERROR = "EVALUATOR_ERROR"


class CallEvaluationStatus(str, Enum):
    TEST_PASSED = "TEST_PASSED"
    TEST_FAILED = "TEST_FAILED"
    PAGE_UNAVAILABLE = "PAGE_UNAVAILABLE"
    TEST_NOT_CONFIGURED = "TEST_NOT_CONFIGURED"
    EVALUATOR_ERROR = "EVALUATOR_ERROR"


class ProcessEvidence(BaseModel):
    command: list[str] = Field(default_factory=list)
    return_code: Optional[int] = None
    duration_ms: int = 0
    stdout_tail: str = ""
    stderr_tail: str = ""


class ComponentMatch(BaseModel):
    component_id: str
    status: MatchStatus
    target_file: Optional[str] = None
    target_symbol: Optional[str] = None
    target_line: Optional[int] = None
    match_type: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class CompileResult(BaseModel):
    entry_file: str
    status: CompileStatus
    evidence: ProcessEvidence = Field(default_factory=ProcessEvidence)
    error: Optional[str] = None


class ComponentEvaluationResult(BaseModel):
    component_id: str
    page_id: str
    status: ComponentEvaluationStatus
    match: ComponentMatch
    compile_result: Optional[CompileResult] = None


class PageEvaluationResult(BaseModel):
    page_id: str
    status: PageEvaluationStatus
    target_file: Optional[str] = None
    compile_result: Optional[CompileResult] = None
    evidence: list[str] = Field(default_factory=list)


class CallEvaluationResult(BaseModel):
    edge_id: str
    source_page: str
    target_page: str
    status: CallEvaluationStatus
    evidence: Optional[ProcessEvidence] = None
    error: Optional[str] = None


class EvaluationSummary(BaseModel):
    component_total: int
    component_compile_passed: int
    component_missing_or_ambiguous: int
    component_compile_failed: int
    component_evaluator_errors: int
    c_cpr: Optional[float]
    c_mr: Optional[float]
    c_cfr: Optional[float]

    page_total: int
    page_compile_passed: int
    page_missing_or_ambiguous: int
    page_compile_failed: int
    page_evaluator_errors: int
    p_cpr: Optional[float]

    call_edge_total: int
    call_test_passed: int
    call_test_failed: int
    call_page_unavailable: int
    call_not_configured: int
    call_evaluator_errors: int
    call_test_coverage: Optional[float]
    pectpr: Optional[float]


class EvaluationReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    method_id: str
    run_id: str
    target_root: str
    component_results: list[ComponentEvaluationResult]
    page_results: list[PageEvaluationResult]
    call_results: list[CallEvaluationResult]
    summary: EvaluationSummary


class VisualIssueCategory(str, Enum):
    COMPONENT = "COMPONENT"
    LAYOUT = "LAYOUT"
    STYLE = "STYLE"
    CONTENT = "CONTENT"
    AESTHETIC = "AESTHETIC"


class VisualIssueSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class VisualEvaluationStatus(str, Enum):
    EVALUATED = "EVALUATED"
    INVALID_COMPARISON = "INVALID_COMPARISON"
    EVALUATOR_ERROR = "EVALUATOR_ERROR"


class VisualDimensionAssessment(BaseModel):
    """单一视觉维度的分数与可复核证据。"""

    score: Optional[float] = Field(ge=0.0, le=100.0)
    rationale: str
    evidence: list[str] = Field(default_factory=list)


class VisualIssue(BaseModel):
    category: VisualIssueCategory
    severity: VisualIssueSeverity
    source_evidence: str
    target_evidence: str
    recommendation: str


class VisualModelAnalysis(BaseModel):
    """视觉模型必须按此结构返回的页面级分析。"""

    comparison_valid: bool
    validity_notes: list[str] = Field(default_factory=list)
    component_fidelity: VisualDimensionAssessment
    layout_fidelity: VisualDimensionAssessment
    style_fidelity: VisualDimensionAssessment
    content_fidelity: VisualDimensionAssessment
    aesthetic_quality: VisualDimensionAssessment
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    strengths: list[str] = Field(default_factory=list)
    issues: list[VisualIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_score_availability(self) -> "VisualModelAnalysis":
        dimensions = (
            self.component_fidelity,
            self.layout_fidelity,
            self.style_fidelity,
            self.content_fidelity,
            self.aesthetic_quality,
        )
        if self.comparison_valid and any(item.score is None for item in dimensions):
            raise ValueError("有效截图对的所有视觉维度都必须给出分数")
        if not self.comparison_valid:
            if not self.validity_notes:
                raise ValueError("无效截图对必须说明不可比较原因")
            if any(item.score is not None for item in dimensions):
                raise ValueError("无效截图对的视觉维度分数必须为 null")
        return self


class VisualImageEvidence(BaseModel):
    path: str
    sha256: str


class VisualPairEvaluationResult(BaseModel):
    pair_id: str
    page_id: str
    state_id: str
    status: VisualEvaluationStatus
    source_image: VisualImageEvidence
    target_image: VisualImageEvidence
    model: str
    prompt_version: str
    overall_fidelity: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    analysis: Optional[VisualModelAnalysis] = None
    error: Optional[str] = None


class VisualEvaluationSummary(BaseModel):
    pair_total: int
    pair_evaluated: int
    pair_invalid: int
    evaluator_errors: int
    visual_pair_coverage: Optional[float]
    mean_component_fidelity: Optional[float]
    mean_layout_fidelity: Optional[float]
    mean_style_fidelity: Optional[float]
    mean_content_fidelity: Optional[float]
    mean_overall_fidelity: Optional[float]
    mean_aesthetic_quality: Optional[float]
    mean_confidence: Optional[float]


class VisualEvaluationReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    method_id: str
    run_id: str
    model: str
    prompt_version: str
    fidelity_weights: dict[str, float]
    pair_results: list[VisualPairEvaluationResult]
    summary: VisualEvaluationSummary
