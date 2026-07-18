"""WPF→React 迁移的分层、只读评测基础设施。"""

from .evaluator import MigrationEvaluator, write_evaluation_outputs
from .manifest_builder import build_evaluation_manifest
from .matcher import ComponentJudge, DeterministicComponentJudge
from .models import (
    CallEdgeSpec,
    CallEvaluationStatus,
    CommandSpec,
    ComponentEvaluationStatus,
    ComponentSpec,
    EvaluationManifest,
    EvaluationReport,
    PageEvaluationStatus,
    PageSpec,
    VisualEvaluationReport,
    VisualEvaluationStatus,
    VisualModelAnalysis,
    VisualPairSpec,
)
from .visual import (
    FIDELITY_WEIGHTS,
    PROMPT_VERSION,
    VisualFidelityJudge,
    VisualMigrationEvaluator,
    write_visual_evaluation_outputs,
)

__all__ = [
    "CallEdgeSpec",
    "CallEvaluationStatus",
    "CommandSpec",
    "ComponentEvaluationStatus",
    "ComponentJudge",
    "ComponentSpec",
    "DeterministicComponentJudge",
    "EvaluationManifest",
    "EvaluationReport",
    "MigrationEvaluator",
    "PageEvaluationStatus",
    "PageSpec",
    "FIDELITY_WEIGHTS",
    "PROMPT_VERSION",
    "VisualEvaluationReport",
    "VisualEvaluationStatus",
    "VisualFidelityJudge",
    "VisualMigrationEvaluator",
    "VisualModelAnalysis",
    "VisualPairSpec",
    "build_evaluation_manifest",
    "write_evaluation_outputs",
    "write_visual_evaluation_outputs",
]
