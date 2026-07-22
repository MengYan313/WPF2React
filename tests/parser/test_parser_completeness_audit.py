"""阶段一解析完整性审计工具的离线回归测试。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.audit_parser_completeness import (
    _artifact_inventory,
    _csharp_audit,
    _file_inventory,
    _rate_from_components,
    _rate_summary,
    _resource_audit,
    _xaml_audit,
)
from scripts.compare_parser_completeness_runs import compare_runs
from src.parser.io_utils import write_json
from src.parser.control_dependency import ControlDependencyAnalyzer
from src.parser.cs_dependency import CsDependencyAnalyzer
from src.parser.cs_parser import CsParser
from src.parser.page_dependency import PageDependencyAnalyzer
from src.parser.resource_dependency import ResourceDependencyAnalyzer
from src.parser.xaml_parser import XamlParser


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "parser"
    / "duplicate-paths"
)


class ParserCompletenessAuditTests(unittest.TestCase):
    def test_parser_rate_uses_inclusive_ninety_percent_threshold(self) -> None:
        at_threshold = _rate_from_components(
            "cs_parser",
            {"sample": {"handled": 9, "total": 10}},
        )
        below_threshold = _rate_from_components(
            "xaml_parser",
            {"sample": {"handled": 89, "total": 100}},
        )
        perfect = _rate_from_components(
            "cs_parser",
            {"sample": {"handled": 100, "total": 100}},
        )

        self.assertTrue(at_threshold["passed"])
        self.assertEqual(at_threshold["percentage"], 90.0)
        self.assertFalse(below_threshold["passed"])
        summary = _rate_summary(
            {"cs_parser": perfect, "xaml_parser": below_threshold}
        )
        self.assertGreater(summary["percentage"], 90.0)
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["below_threshold"], ["xaml_parser"])

    def test_duplicate_path_fixture_has_closed_file_and_resource_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "repos" / "DuplicatePaths"
            outputs = root / "outputs"
            project_output = outputs / "DuplicatePaths"
            shutil.copytree(FIXTURE_ROOT, project)

            CsParser.parse_project(str(project), str(outputs))
            XamlParser.parse_project(str(project), str(outputs))
            CsDependencyAnalyzer.analyze_project("DuplicatePaths", str(outputs))
            PageDependencyAnalyzer.analyze_project("DuplicatePaths", str(outputs))
            ControlDependencyAnalyzer.analyze_project_static(
                "DuplicatePaths", str(outputs)
            )
            ResourceDependencyAnalyzer.analyze_project(
                "DuplicatePaths", str(project), str(outputs)
            )

            cs_files, xaml_files, csproj_files, filtered = _file_inventory(project)
            files = _artifact_inventory(
                project,
                project_output,
                cs_files,
                xaml_files,
                csproj_files,
                filtered,
            )
            xaml, _, resource_keys, _ = _xaml_audit(
                project, project_output, xaml_files
            )
            csharp, unresolved, _ = _csharp_audit(
                project, project_output, cs_files
            )
            resources, resource_unresolved = _resource_audit(
                project,
                project_output,
                xaml_files,
                csproj_files,
                resource_keys,
            )

            self.assertEqual(files["eligible_source_files"], 7)
            self.assertEqual(files["successful_artifacts"], 7)
            self.assertEqual(files["unique_source_ids"], 7)
            self.assertEqual(files["unique_output_paths"], 7)
            self.assertEqual(files["missing_artifacts"], 0)
            self.assertEqual(files["output_collisions"], 0)

            self.assertEqual(xaml["raw_xml_elements"], 8)
            self.assertEqual(xaml["xaml_ir_nodes"], 8)
            self.assertEqual(xaml["silently_unclassified_nodes"], 0)
            self.assertEqual(xaml["occurrences"]["event_handler"], 1)
            self.assertEqual(xaml["occurrences"]["file_resource_reference"], 2)

            self.assertEqual(csharp["tree_sitter_roots"], 4)
            self.assertEqual(csharp["tree_sitter_error_nodes"], 0)
            self.assertEqual(csharp["duplicate_type_groups"], 2)
            self.assertEqual(csharp["candidate_dependency_edges"], 0)
            self.assertEqual(unresolved, [])

            self.assertEqual(resources["repository_resource_files"], 2)
            self.assertEqual(resources["declared_resource_source_ids"], 2)
            self.assertEqual(resources["xaml_file_references"], 2)
            self.assertEqual(resources["resolved_references"], 2)
            self.assertEqual(resources["unexplained_references"], 0)
            self.assertEqual(resource_unresolved, [])

    def test_audit_output_is_deterministic_for_same_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "DuplicatePaths"
            outputs = root / "outputs"
            project_output = outputs / "DuplicatePaths"
            shutil.copytree(FIXTURE_ROOT, project)
            CsParser.parse_project(str(project), str(outputs))
            XamlParser.parse_project(str(project), str(outputs))

            cs_files, xaml_files, _, _ = _file_inventory(project)
            first_xaml = _xaml_audit(project, project_output, xaml_files)
            second_xaml = _xaml_audit(project, project_output, xaml_files)
            first_csharp = _csharp_audit(project, project_output, cs_files)
            second_csharp = _csharp_audit(project, project_output, cs_files)

            self.assertEqual(first_xaml, second_xaml)
            self.assertEqual(first_csharp, second_csharp)

    def test_run_comparison_normalizes_only_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "after-run-1"
            second = root / "after-run-2"
            write_json(
                first / "Demo" / "dependency" / "sample.json",
                {
                    "output_path": f"{first.as_posix()}/Demo/result.json",
                    "ordered": ["A", "B"],
                },
            )
            write_json(
                second / "Demo" / "dependency" / "sample.json",
                {
                    "output_path": f"{second.as_posix()}/Demo/result.json",
                    "ordered": ["A", "B"],
                },
            )
            write_json(first / "run_index.json", {"elapsed": 1.0})
            write_json(second / "run_index.json", {"elapsed": 9.0})

            matching = compare_runs(first, second)
            self.assertTrue(matching["deterministic"])
            self.assertEqual(matching["matching_artifact_count"], 1)

            write_json(
                second / "Demo" / "dependency" / "sample.json",
                {
                    "output_path": f"{second.as_posix()}/Demo/result.json",
                    "ordered": ["B", "A"],
                },
            )
            changed = compare_runs(first, second)
            self.assertFalse(changed["deterministic"])
            self.assertEqual(
                [item["path"] for item in changed["content_mismatches"]],
                ["Demo/dependency/sample.json"],
            )


if __name__ == "__main__":
    unittest.main()
