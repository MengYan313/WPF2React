"""人工截图对视觉评测的确定性离线测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from autogen_core import Image
from PIL import Image as PILImage

from src.migration.evaluation import (
    EvaluationManifest,
    PageSpec,
    VisualEvaluationStatus,
    VisualMigrationEvaluator,
    VisualPairSpec,
    write_visual_evaluation_outputs,
)


class _FakeModelClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def create(self, *, messages, extra_create_args):
        self.calls.append(
            {
                "messages": messages,
                "extra_create_args": extra_create_args,
            }
        )
        return SimpleNamespace(content=self.responses.pop(0))


def _dimension(score: float | None, rationale: str) -> dict[str, object]:
    return {
        "score": score,
        "rationale": rationale,
        "evidence": [rationale],
    }


def _valid_analysis() -> dict[str, object]:
    return {
        "comparison_valid": True,
        "validity_notes": [],
        "component_fidelity": _dimension(90, "可见控件基本齐全"),
        "layout_fidelity": _dimension(80, "主要分区一致"),
        "style_fidelity": _dimension(70, "字体和颜色仍有差异"),
        "content_fidelity": _dimension(100, "可见文本一致"),
        "aesthetic_quality": _dimension(60, "目标页面视觉层次一般"),
        "confidence": 0.9,
        "summary": "结构忠实，样式仍需调整。",
        "strengths": ["内容完整"],
        "issues": [
            {
                "category": "STYLE",
                "severity": "MINOR",
                "source_evidence": "原图标题字号较大",
                "target_evidence": "目标图标题字号偏小",
                "recommendation": "增大标题字号",
            }
        ],
    }


class VisualEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_multimodal_pair_generates_weighted_report_and_evidence(self):
        with tempfile.TemporaryDirectory(prefix="wpf2react-visual-") as temp_dir:
            workspace = Path(temp_dir)
            self._write_images(workspace)
            fake_client = _FakeModelClient(
                [json.dumps(_valid_analysis(), ensure_ascii=False)]
            )
            evaluator = VisualMigrationEvaluator(
                self._manifest(),
                workspace_root=workspace,
                model_client=fake_client,
                model_name="fake-vision-model",
            )

            report = await evaluator.evaluate(method_id="MethodA", run_id="seed-1")

            self.assertEqual(report.pair_results[0].status, VisualEvaluationStatus.EVALUATED)
            self.assertAlmostEqual(report.pair_results[0].overall_fidelity or 0, 84.5)
            self.assertAlmostEqual(report.summary.mean_overall_fidelity or 0, 84.5)
            self.assertEqual(report.summary.mean_aesthetic_quality, 60)
            self.assertEqual(report.fidelity_weights["component_fidelity"], 0.35)

            user_content = fake_client.calls[0]["messages"][1].content
            self.assertEqual(sum(isinstance(item, Image) for item in user_content), 2)
            self.assertEqual(
                fake_client.calls[0]["extra_create_args"]["response_format"],
                {"type": "json_object"},
            )

            report_path, records_path = write_visual_evaluation_outputs(
                report,
                workspace / "output",
            )
            self.assertTrue(report_path.is_file())
            record = json.loads(records_path.read_text(encoding="utf-8"))
            self.assertEqual(record["unit_type"], "visual_pair")
            self.assertEqual(record["source_image"]["path"], "before.png")

    async def test_invalid_first_json_is_repaired_at_most_once(self):
        with tempfile.TemporaryDirectory(prefix="wpf2react-visual-") as temp_dir:
            workspace = Path(temp_dir)
            self._write_images(workspace)
            fake_client = _FakeModelClient(
                ["not-json", json.dumps(_valid_analysis(), ensure_ascii=False)]
            )
            evaluator = VisualMigrationEvaluator(
                self._manifest(),
                workspace_root=workspace,
                model_client=fake_client,
                model_name="fake-vision-model",
            )

            report = await evaluator.evaluate(method_id="MethodA", run_id="seed-1")

            self.assertEqual(report.pair_results[0].status, VisualEvaluationStatus.EVALUATED)
            self.assertEqual(len(fake_client.calls), 2)
            repair_content = fake_client.calls[1]["messages"][1].content
            self.assertIsInstance(repair_content, str)
            self.assertIn("损坏响应", repair_content)

    async def test_unusable_pair_is_excluded_from_score_aggregation(self):
        with tempfile.TemporaryDirectory(prefix="wpf2react-visual-") as temp_dir:
            workspace = Path(temp_dir)
            self._write_images(workspace)
            invalid = {
                "comparison_valid": False,
                "validity_notes": ["两张截图不是同一页面状态"],
                "component_fidelity": _dimension(None, "不评分"),
                "layout_fidelity": _dimension(None, "不评分"),
                "style_fidelity": _dimension(None, "不评分"),
                "content_fidelity": _dimension(None, "不评分"),
                "aesthetic_quality": _dimension(None, "不评分"),
                "confidence": 0.95,
                "summary": "截图不可比较。",
                "strengths": [],
                "issues": [],
            }
            evaluator = VisualMigrationEvaluator(
                self._manifest(),
                workspace_root=workspace,
                model_client=_FakeModelClient([json.dumps(invalid, ensure_ascii=False)]),
                model_name="fake-vision-model",
            )

            report = await evaluator.evaluate(method_id="MethodA", run_id="seed-1")

            self.assertEqual(
                report.pair_results[0].status,
                VisualEvaluationStatus.INVALID_COMPARISON,
            )
            self.assertIsNone(report.pair_results[0].overall_fidelity)
            self.assertEqual(report.summary.pair_invalid, 1)
            self.assertEqual(report.summary.visual_pair_coverage, 0.0)
            self.assertIsNone(report.summary.mean_component_fidelity)

    async def test_missing_image_is_evaluator_error_without_model_call(self):
        with tempfile.TemporaryDirectory(prefix="wpf2react-visual-") as temp_dir:
            workspace = Path(temp_dir)
            self._write_images(workspace)
            manifest = self._manifest()
            manifest.visual_pairs[0].source_image = "missing.png"
            fake_client = _FakeModelClient([])
            evaluator = VisualMigrationEvaluator(
                manifest,
                workspace_root=workspace,
                model_client=fake_client,
                model_name="fake-vision-model",
            )

            report = await evaluator.evaluate(method_id="MethodA", run_id="seed-1")

            result = report.pair_results[0]
            self.assertEqual(result.status, VisualEvaluationStatus.EVALUATOR_ERROR)
            self.assertEqual(result.source_image.path, "missing.png")
            self.assertIn("FileNotFoundError", result.error or "")
            self.assertEqual(fake_client.calls, [])

    @staticmethod
    def _write_images(workspace: Path) -> None:
        PILImage.new("RGB", (4, 4), color="white").save(workspace / "before.png")
        PILImage.new("RGB", (4, 4), color="black").save(workspace / "after.png")

    @staticmethod
    def _manifest() -> EvaluationManifest:
        return EvaluationManifest(
            project_id="Synthetic",
            target_root="results/Synthetic",
            pages=[
                PageSpec(
                    page_id="MainWindow.xaml",
                    source_file="repos/Synthetic/MainWindow.xaml",
                )
            ],
            visual_pairs=[
                VisualPairSpec(
                    pair_id="MainWindow-default",
                    page_id="MainWindow.xaml",
                    state_id="default",
                    source_image="before.png",
                    target_image="after.png",
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
