"""分层迁移评测的确定性离线测试。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from src.migration.evaluation import (
    CallEdgeSpec,
    CallEvaluationStatus,
    CommandSpec,
    ComponentEvaluationStatus,
    ComponentSpec,
    EvaluationManifest,
    MigrationEvaluator,
    PageEvaluationStatus,
    PageSpec,
    build_evaluation_manifest,
    write_evaluation_outputs,
)


class LayeredEvaluationTests(unittest.TestCase):
    def test_three_layers_keep_fixed_denominators_and_failure_reasons(self):
        with tempfile.TemporaryDirectory(prefix="wpf2react-evaluation-") as temp_dir:
            workspace = Path(temp_dir)
            target = workspace / "target"
            target.mkdir()
            (target / "tests").mkdir()

            (target / "PageA.tsx").write_text(
                "export function PageA() { return <Box><Button>Go</Button></Box>; }\n",
                encoding="utf-8",
            )
            (target / "PageB.tsx").write_text(
                "export function PageB() { return <Box>BROKEN_TOKEN</Box>; }\n",
                encoding="utf-8",
            )
            (target / "PageD.tsx").write_text(
                "export function PageD() { return <Box />; }\n",
                encoding="utf-8",
            )
            for name in ("a_to_d.test.tsx", "a_to_b.test.tsx", "d_to_c.test.tsx"):
                (target / "tests" / name).write_text("PASS\n", encoding="utf-8")

            compiler_helper = workspace / "fake_compiler.py"
            compiler_helper.write_text(
                """from pathlib import Path
import sys
content = Path(sys.argv[1]).read_text(encoding='utf-8')
raise SystemExit(1 if 'BROKEN_TOKEN' in content else 0)
""",
                encoding="utf-8",
            )
            call_helper = workspace / "fake_call_test.py"
            call_helper.write_text(
                """from pathlib import Path
import sys
content = Path(sys.argv[1]).read_text(encoding='utf-8')
raise SystemExit(0 if 'PASS' in content else 1)
""",
                encoding="utf-8",
            )

            manifest = EvaluationManifest(
                project_id="Synthetic",
                target_root="target",
                compiler=CommandSpec(
                    command=[sys.executable, str(compiler_helper), "{entry}"]
                ),
                call_tester=CommandSpec(
                    command=[sys.executable, str(call_helper), "{test_file}"]
                ),
                pages=[
                    self._page("PageA"),
                    self._page("PageB"),
                    self._page("PageC"),
                    self._page("PageD"),
                ],
                components=[
                    self._component("PageA:root", "PageA", "Grid", "Box"),
                    self._component("PageA:root.0", "PageA", "Button", "Button"),
                    self._component("PageB:root", "PageB", "Grid", "Box"),
                    self._component("PageC:root", "PageC", "Grid", "Box"),
                    self._component("PageD:root", "PageD", "Grid", "Box"),
                ],
                call_edges=[
                    CallEdgeSpec(
                        edge_id="PageA->PageD",
                        source_page="PageA.xaml",
                        target_page="PageD.xaml",
                        test_file="tests/a_to_d.test.tsx",
                    ),
                    CallEdgeSpec(
                        edge_id="PageA->PageB",
                        source_page="PageA.xaml",
                        target_page="PageB.xaml",
                        test_file="tests/a_to_b.test.tsx",
                    ),
                    CallEdgeSpec(
                        edge_id="PageD->PageC",
                        source_page="PageD.xaml",
                        target_page="PageC.xaml",
                        test_file="tests/d_to_c.test.tsx",
                    ),
                ],
            )

            report = MigrationEvaluator(
                manifest,
                workspace_root=workspace,
            ).evaluate(method_id="SyntheticMethod", run_id="run-1")

            self.assertEqual(report.summary.component_total, 5)
            self.assertEqual(report.summary.component_compile_passed, 3)
            self.assertEqual(report.summary.component_compile_failed, 1)
            self.assertEqual(report.summary.component_missing_or_ambiguous, 1)
            self.assertAlmostEqual(report.summary.c_cpr or 0.0, 0.6)
            self.assertAlmostEqual(report.summary.c_mr or 0.0, 0.2)
            self.assertAlmostEqual(report.summary.c_cfr or 0.0, 0.2)

            component_statuses = {
                result.component_id: result.status
                for result in report.component_results
            }
            self.assertEqual(
                component_statuses["PageB:root"],
                ComponentEvaluationStatus.COMPILE_FAILED,
            )
            self.assertEqual(
                component_statuses["PageC:root"],
                ComponentEvaluationStatus.NOT_FOUND,
            )

            self.assertEqual(report.summary.page_total, 4)
            self.assertEqual(report.summary.page_compile_passed, 2)
            self.assertEqual(report.summary.page_compile_failed, 1)
            self.assertEqual(report.summary.page_missing_or_ambiguous, 1)
            self.assertAlmostEqual(report.summary.p_cpr or 0.0, 0.5)

            call_statuses = {
                result.edge_id: result.status for result in report.call_results
            }
            self.assertEqual(
                call_statuses["PageA->PageD"],
                CallEvaluationStatus.TEST_PASSED,
            )
            self.assertEqual(
                call_statuses["PageA->PageB"],
                CallEvaluationStatus.PAGE_UNAVAILABLE,
            )
            self.assertEqual(
                call_statuses["PageD->PageC"],
                CallEvaluationStatus.PAGE_UNAVAILABLE,
            )
            self.assertAlmostEqual(report.summary.call_test_coverage or 0.0, 1.0)
            self.assertAlmostEqual(report.summary.pectpr or 0.0, 1 / 3)

            report_path, records_path = write_evaluation_outputs(
                report,
                workspace / "evaluation-output",
            )
            self.assertTrue(report_path.is_file())
            records = records_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(records), 5 + 4 + 3)
            self.assertEqual(json.loads(records[0])["unit_type"], "component")

    def test_missing_toolchain_is_evaluator_error_not_compile_failure(self):
        with tempfile.TemporaryDirectory(prefix="wpf2react-evaluation-") as temp_dir:
            workspace = Path(temp_dir)
            target = workspace / "target"
            target.mkdir()
            (target / "OnlyPage.tsx").write_text(
                "export function OnlyPage() { return <Box />; }\n",
                encoding="utf-8",
            )
            manifest = EvaluationManifest(
                project_id="Synthetic",
                target_root="target",
                pages=[self._page("OnlyPage")],
                components=[
                    self._component("OnlyPage:root", "OnlyPage", "Grid", "Box")
                ],
            )

            report = MigrationEvaluator(
                manifest,
                workspace_root=workspace,
            ).evaluate(method_id="SyntheticMethod", run_id="run-1")

            self.assertEqual(
                report.component_results[0].status,
                ComponentEvaluationStatus.EVALUATOR_ERROR,
            )
            self.assertEqual(
                report.page_results[0].status,
                PageEvaluationStatus.EVALUATOR_ERROR,
            )
            self.assertIsNone(report.summary.c_cpr)
            self.assertIsNone(report.summary.p_cpr)

    def test_unconfigured_call_edge_keeps_pectpr_unavailable(self):
        with tempfile.TemporaryDirectory(prefix="wpf2react-evaluation-") as temp_dir:
            workspace = Path(temp_dir)
            target = workspace / "target"
            target.mkdir()
            for page_id in ("PageA", "PageB"):
                (target / f"{page_id}.tsx").write_text(
                    f"export function {page_id}() {{ return <Box />; }}\n",
                    encoding="utf-8",
                )
            compiler_helper = workspace / "fake_compiler.py"
            compiler_helper.write_text(
                "import sys\nraise SystemExit(0)\n",
                encoding="utf-8",
            )
            manifest = EvaluationManifest(
                project_id="Synthetic",
                target_root="target",
                compiler=CommandSpec(
                    command=[sys.executable, str(compiler_helper), "{entry}"]
                ),
                pages=[self._page("PageA"), self._page("PageB")],
                call_edges=[
                    CallEdgeSpec(
                        edge_id="PageA->PageB",
                        source_page="PageA.xaml",
                        target_page="PageB.xaml",
                    )
                ],
            )

            report = MigrationEvaluator(
                manifest,
                workspace_root=workspace,
            ).evaluate(method_id="SyntheticMethod", run_id="run-1")

            self.assertEqual(
                report.call_results[0].status,
                CallEvaluationStatus.TEST_NOT_CONFIGURED,
            )
            self.assertEqual(report.summary.call_test_coverage, 0.0)
            self.assertIsNone(report.summary.pectpr)

    def test_manifest_builder_extracts_components_pages_and_call_edges(self):
        with tempfile.TemporaryDirectory(prefix="wpf2react-manifest-") as temp_dir:
            workspace = Path(temp_dir)
            dependency = workspace / "outputs" / "Demo" / "dependency"
            dependency.mkdir(parents=True)
            mapping = workspace / "mapping.json"
            mapping.write_text(
                json.dumps(
                    {
                        "Grid": {"mui_component": "Box"},
                        "Button": {"mui_component": "Button"},
                    }
                ),
                encoding="utf-8",
            )
            (dependency / "page_dependency.json").write_text(
                json.dumps(
                    {
                        "pages": {
                            "Main.xaml": {
                                "xaml_file": "repos/Demo/Main.xaml",
                                "control_file": "dependency/controls/Main.xaml.json",
                                "dependencies": ["Child.xaml"],
                            },
                            "Child.xaml": {
                                "xaml_file": "repos/Demo/Child.xaml",
                                "control_file": "dependency/controls/Child.xaml.json",
                                "dependencies": [],
                            },
                        },
                        "migration_order": ["Child.xaml", "Main.xaml"],
                    }
                ),
                encoding="utf-8",
            )
            self._write_control(
                dependency / "controls" / "Main.xaml.json",
                "repos/Demo/Main.xaml",
                {
                    "tag": "Grid",
                    "attributes": {},
                    "source_code": "<Grid><Button Name=\"Open\" Content=\"Open\" /></Grid>",
                    "children": [
                        {
                            "tag": "Button",
                            "attributes": {"Name": "Open", "Content": "Open"},
                            "source_code": "<Button Name=\"Open\" Content=\"Open\" />",
                            "children": [],
                        }
                    ],
                },
                2,
            )
            self._write_control(
                dependency / "controls" / "Child.xaml.json",
                "repos/Demo/Child.xaml",
                {
                    "tag": "Grid",
                    "attributes": {},
                    "source_code": "<Grid />",
                    "children": [],
                },
                1,
            )

            manifest = build_evaluation_manifest(
                "Demo",
                output_base_dir=workspace / "outputs",
                target_root="results/Demo",
                mapping_path=mapping,
            )

            self.assertEqual(
                [page.page_id for page in manifest.pages],
                ["Child.xaml", "Main.xaml"],
            )
            self.assertEqual(len(manifest.components), 3)
            self.assertEqual(manifest.components[-1].source_name, "Open")
            self.assertIn("Button", manifest.components[-1].target_tag_hints)
            self.assertEqual(len(manifest.call_edges), 1)
            self.assertEqual(
                manifest.call_edges[0].edge_id,
                "Main.xaml->Child.xaml",
            )
            self.assertEqual(manifest.metadata["review_status"], "unreviewed")

            filtered = build_evaluation_manifest(
                "Demo",
                output_base_dir=workspace / "outputs",
                target_root="results/Demo",
                mapping_path=mapping,
                page_names=["Main.xaml"],
            )
            self.assertEqual([page.page_id for page in filtered.pages], ["Main.xaml"])
            self.assertEqual(filtered.call_edges, [])

            audited = build_evaluation_manifest(
                "Demo",
                output_base_dir=workspace / "outputs",
                target_root="results/Demo",
                mapping_path=mapping,
                page_names=["Main.xaml", "Child.xaml"],
                audited_call_edges=[
                    {
                        "source": "Child.xaml",
                        "target": "Main.xaml",
                        "relation": "dialog_navigation",
                        "confidence": "high",
                    }
                ],
            )
            self.assertEqual(len(audited.call_edges), 2)
            self.assertEqual(audited.call_edges[-1].call_type, "dialog_navigation")

    @staticmethod
    def _page(page_id: str) -> PageSpec:
        page_id = page_id if page_id.endswith(".xaml") else f"{page_id}.xaml"
        target_file = f"{page_id.removesuffix('.xaml')}.tsx"
        return PageSpec(
            page_id=page_id,
            source_file=f"repos/{page_id}",
            target_file_hints=[target_file],
        )

    @staticmethod
    def _component(
        component_id: str,
        page_id: str,
        source_tag: str,
        target_tag: str,
    ) -> ComponentSpec:
        page_id = page_id if page_id.endswith(".xaml") else f"{page_id}.xaml"
        target_file = f"{page_id.removesuffix('.xaml')}.tsx"
        return ComponentSpec(
            component_id=component_id,
            page_id=page_id,
            source_file=f"repos/{page_id}",
            source_node_path=component_id.split(":", 1)[1],
            source_tag=source_tag,
            target_file_hints=[target_file],
            target_tag_hints=[target_tag],
        )

    @staticmethod
    def _write_control(
        path: Path,
        source_file: str,
        controls: dict[str, object],
        count: int,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        page_id = path.relative_to(path.parents[2]).as_posix()
        page_id = page_id.removeprefix("dependency/controls/").removesuffix(".json")
        path.write_text(
            json.dumps(
                {
                    "page_id": page_id,
                    "source_id": page_id,
                    "source_file": source_file,
                    "control_count": count,
                    "controls": controls,
                }
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
