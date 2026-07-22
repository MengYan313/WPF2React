"""数据集全量基线发现的解析器通用回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.common.source_identity import SourceIdentityError
from src.parser.cs_dependency import CsDependencyAnalyzer
from src.parser.cs_parser import CsParser
from src.parser.control_dependency import ControlDependencyAnalyzer
from src.parser.io_utils import read_json, write_json
from src.parser.page_dependency import PageDependencyAnalyzer
from src.parser.path_utils import discover_project_files
from src.parser.resource_dependency import ResourceDependencyAnalyzer
from src.parser.xaml_parser import XamlParser
from src.migration.evaluation import build_evaluation_manifest


class SourceDiscoveryTests(unittest.TestCase):
    def test_generated_directories_and_symlinks_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "ViewModels").mkdir()
            (root / "obj" / "Debug").mkdir(parents=True)
            (root / "Generated Files").mkdir()
            source = root / "ViewModels" / "MainViewModel.cs"
            source.write_text("class MainViewModel {}", encoding="utf-8")
            (root / "obj" / "Debug" / "Generated.cs").write_text(
                "class Generated {}", encoding="utf-8"
            )
            (root / "Generated Files" / "Interop.cs").write_text(
                "class Interop {}", encoding="utf-8"
            )
            (root / "Linked.cs").symlink_to(source)

            self.assertEqual(
                discover_project_files(root, [".cs"]),
                [source],
            )


class RelativePathIdentityTests(unittest.TestCase):
    def test_legacy_flat_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "Legacy" / "cs" / "Shared.cs.json"
            write_json(
                artifact,
                {
                    "type": "else",
                    "source_file": "repos/Legacy/A/Shared.cs",
                },
            )
            analyzer = CsDependencyAnalyzer("Legacy", temp_dir)
            with self.assertRaisesRegex(SourceIdentityError, "id_scheme"):
                analyzer.load_cs_files()

    def test_duplicate_basenames_remain_distinct_through_parser_and_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "repos" / "DuplicateNames"
            outputs = root / "outputs"
            for directory, namespace in (("A", "Alpha"), ("B", "Beta")):
                source_dir = project / directory
                source_dir.mkdir(parents=True)
                (source_dir / "Shared.cs").write_text(
                    f"namespace {namespace} {{ public class Shared {{}} }}",
                    encoding="utf-8",
                )
                (source_dir / "View.xaml").write_text(
                    '<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" '
                    'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" '
                    f'x:Class="{namespace}.View"><Grid /></Window>',
                    encoding="utf-8",
                )
                code_behind_name = "VIew.xaml.cs" if directory == "B" else "View.xaml.cs"
                (source_dir / code_behind_name).write_text(
                    f"namespace {namespace} {{ public partial class View {{}} }}",
                    encoding="utf-8",
                )

            cs_results = CsParser.parse_project(str(project), str(outputs))
            xaml_results = XamlParser.parse_project(
                str(project), str(outputs), include_csproj=False
            )
            self.assertEqual(len(cs_results), 4)
            self.assertEqual(len(set(cs_results.values())), 4)
            self.assertEqual(len(set(xaml_results.values())), 2)
            self.assertTrue(
                (outputs / "DuplicateNames" / "cs" / "A" / "Shared.cs.json").is_file()
            )
            self.assertTrue(
                (outputs / "DuplicateNames" / "xaml" / "B" / "View.xaml.json").is_file()
            )
            self.assertEqual(
                read_json(outputs / "DuplicateNames" / "cs" / "B" / "Shared.cs.json")[
                    "source_id"
                ],
                "B/Shared.cs",
            )

            cs_graph, _ = CsDependencyAnalyzer.analyze_project(
                "DuplicateNames", str(outputs)
            )
            page_graph, _ = PageDependencyAnalyzer.analyze_project(
                "DuplicateNames", str(outputs)
            )
            controls = ControlDependencyAnalyzer.analyze_project_static(
                "DuplicateNames", str(outputs)
            )

            self.assertEqual(set(cs_graph["files"]), {"A/Shared.cs", "B/Shared.cs"})
            self.assertEqual(
                set(page_graph["pages"]), {"A/View.xaml", "B/View.xaml"}
            )
            self.assertEqual(set(controls), {"A/View.xaml", "B/View.xaml"})
            self.assertTrue(
                (
                    outputs
                    / "DuplicateNames"
                    / "dependency"
                    / "controls"
                    / "A"
                    / "View.xaml.json"
                ).is_file()
            )

            manifest = build_evaluation_manifest(
                "DuplicateNames",
                output_base_dir=outputs,
                target_root=root / "results" / "DuplicateNames",
                mapping_path=root / "missing-mapping.json",
            )
            self.assertEqual(
                {page.page_id for page in manifest.pages},
                {"A/View.xaml", "B/View.xaml"},
            )
            self.assertEqual(
                {tuple(page.target_file_hints) for page in manifest.pages},
                {
                    ("A/View.tsx", "src/A/View.tsx", "src/pages/A/View.tsx"),
                    ("B/View.tsx", "src/B/View.tsx", "src/pages/B/View.tsx"),
                },
            )


class FileCompatibilityTests(unittest.TestCase):
    def test_windows_1252_csharp_source_is_decoded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Legacy.cs"
            source.write_bytes(b"// legacy \x95 comment\npublic class Legacy {}\n")

            parser = CsParser()
            root = parser.parse_file(str(source))

            self.assertEqual(root.node_type, "compilation_unit")
            self.assertIn("legacy", parser.source_lines[0])

    def test_custom_application_root_is_not_counted_as_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            xaml_path = Path(temp_dir) / "App.xaml"
            xaml_path.write_text(
                '<local:MvxApplication xmlns:local="urn:test" />',
                encoding="utf-8",
            )

            parser = XamlParser()
            parser.parse_file(str(xaml_path))

            self.assertEqual(parser.file_type, "root")


class CsDependencyTests(unittest.TestCase):
    def test_combined_source_patterns_preserve_reference_semantics(self) -> None:
        analyzer = CsDependencyAnalyzer("Synthetic")
        source = """
            var one = new Foo();
            FooBar.Create();
            class Child : Baz {}
            Dictionary<Foo, Baz> values;
        """

        references = analyzer.find_type_references_in_source(
            source, {"Foo", "FooBar", "Baz", "Unused"}
        )

        self.assertEqual(references, {"Foo", "FooBar", "Baz"})

    def test_cycle_groups_are_condensed_into_deterministic_order(self) -> None:
        analyzer = CsDependencyAnalyzer("Synthetic")
        analyzer.cs_files = {
            name: {"source_file": f"{name}.cs", "type": "else", "data": {}}
            for name in ["C", "A", "D", "B"]
        }
        analyzer.dependencies = {
            "A": ["B"],
            "B": ["A"],
            "C": ["B"],
        }

        order = analyzer.generate_migration_order()

        self.assertEqual(order, ["D", "A", "B", "C"])
        self.assertEqual(analyzer.cycle_groups, [["A", "B"]])


class ResourceDependencyTests(unittest.TestCase):
    def test_missing_project_file_produces_explicit_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = ResourceDependencyAnalyzer(temp_dir)
            result = analyzer.analyze_project_resources("NoProject")

            self.assertTrue(result["project_file_missing"])
            self.assertEqual(result["csproj_files"], [])
            self.assertEqual(result["resources"], [])

    def test_multiple_project_files_are_merged_and_verified_from_their_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "outputs"
            project_root = root / "repos" / "MultiProject"
            xaml_output = output_root / "MultiProject" / "xaml"
            for name in ["A", "B"]:
                source_dir = project_root / name
                source_dir.mkdir(parents=True)
                csproj_path = source_dir / f"{name}.csproj"
                csproj_path.write_text("<Project />", encoding="utf-8")
                (source_dir / f"{name}.png").write_bytes(b"png")
                write_json(
                    xaml_output / f"{name}.csproj.json",
                    {
                        "source_file": str(csproj_path),
                        "root": {
                            "tag": "Project",
                            "attributes": {},
                            "children": [
                                {
                                    "tag": "Resource",
                                    "attributes": {"Include": f"{name}.png"},
                                    "children": [],
                                }
                            ],
                        },
                    },
                )

            analyzer = ResourceDependencyAnalyzer(str(output_root))
            result = analyzer.analyze_project_resources(
                "MultiProject", str(project_root)
            )

            self.assertFalse(result["project_file_missing"])
            self.assertEqual(len(result["csproj_files"]), 2)
            self.assertEqual(result["total_resources"], 2)
            self.assertTrue(all(item["exists"] for item in result["resources"]))
            analyzer.save_to_json("MultiProject")

    def test_batch_index_preserves_indirect_style_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "outputs"
            project_root = root / "repos" / "StyledProject"
            dependency_dir = output_root / "StyledProject" / "dependency"
            xaml_output = output_root / "StyledProject" / "xaml"
            project_root.mkdir(parents=True)
            csproj_path = project_root / "StyledProject.csproj"
            csproj_path.write_text("<Project />", encoding="utf-8")
            (project_root / "icon.png").write_bytes(b"png")
            write_json(
                xaml_output / "StyledProject.csproj.json",
                {
                    "id_scheme": "repository-relative-posix-v1",
                    "source_id": "StyledProject.csproj",
                    "source_file": str(csproj_path),
                    "root": {
                        "tag": "Project",
                        "attributes": {},
                        "children": [
                            {
                                "tag": "Resource",
                                "attributes": {"Include": "icon.png"},
                                "children": [],
                            }
                        ],
                    },
                },
            )
            write_json(
                dependency_dir / "page_dependency.json",
                {
                    "id_scheme": "repository-relative-posix-v1",
                    "pages": {
                        "Main.xaml": {
                            "xaml_file": str(project_root / "Main.xaml")
                        }
                    }
                },
            )
            write_json(
                dependency_dir / "indirect_resources.json",
                {
                    "resources": [
                        {
                            "tag": "Style",
                            "key": "PictureStyle",
                            "source_code": '<Image Source="icon.png" />',
                        }
                    ]
                },
            )
            write_json(
                xaml_output / "Main.xaml.json",
                {
                    "id_scheme": "repository-relative-posix-v1",
                    "source_id": "Main.xaml",
                    "root": {
                        "tag": "Button",
                        "attributes": {
                            "Style": "{StaticResource PictureStyle}"
                        },
                        "source_code": '<Button Style="{StaticResource PictureStyle}" />',
                        "children": [],
                    }
                },
            )

            analyzer = ResourceDependencyAnalyzer(str(output_root))
            result = analyzer.analyze_project_resources(
                "StyledProject", str(project_root)
            )

            references = result["resources"][0]["referenced_by_pages"]
            self.assertEqual(len(references), 1)
            self.assertEqual(references[0]["style_references"], ["PictureStyle"])


if __name__ == "__main__":
    unittest.main()
