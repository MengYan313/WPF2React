"""数据集全量基线发现的解析器通用回归测试。"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from src.common.source_identity import (
    SourceIdentityError,
    mirrored_json_path,
    target_relative_path,
)
from src.parser.cs_dependency import CsDependencyAnalyzer
from src.parser.cs_parser import CsParser
from src.parser.control_dependency import ControlDependencyAnalyzer
from src.parser.io_utils import read_json, write_json
from src.parser.page_dependency import PageDependencyAnalyzer
from src.parser.path_utils import discover_project_files
from src.parser.resource_dependency import ResourceDependencyAnalyzer
from src.parser.xaml_parser import XamlParser
from src.migration.evaluation import (
    CommandSpec,
    MigrationEvaluator,
    PageEvaluationStatus,
    build_evaluation_manifest,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "parser"
    / "duplicate-paths"
)
MISSING_CSPROJ_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "parser"
    / "missing-csproj"
)


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

    def test_duplicate_path_fixture_preserves_the_complete_identity_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "repos" / "DuplicatePaths"
            outputs = root / "outputs"
            results = root / "results" / "DuplicatePaths"
            shutil.copytree(FIXTURE_ROOT, project)

            cs_results = CsParser.parse_project(str(project), str(outputs))
            xaml_results = XamlParser.parse_project(str(project), str(outputs))
            cs_graph, _ = CsDependencyAnalyzer.analyze_project(
                "DuplicatePaths", str(outputs)
            )
            page_graph, _ = PageDependencyAnalyzer.analyze_project(
                "DuplicatePaths", str(outputs)
            )
            controls = ControlDependencyAnalyzer.analyze_project_static(
                "DuplicatePaths", str(outputs)
            )
            resource_graph, _ = ResourceDependencyAnalyzer.analyze_project(
                "DuplicatePaths", str(project), str(outputs)
            )

            self.assertEqual(len(cs_results), 4)
            self.assertEqual(len(set(cs_results.values())), 4)
            self.assertEqual(len(xaml_results), 3)
            self.assertEqual(len(set(xaml_results.values())), 3)
            self.assertEqual(
                set(cs_graph["files"]),
                {"Models/Admin/Shared.cs", "Models/User/Shared.cs"},
            )

            expected_pages = {
                "Views/Admin/MainWindow.xaml",
                "Views/User/MainWindow.xaml",
            }
            self.assertEqual(set(page_graph["pages"]), expected_pages)
            self.assertEqual(set(controls), expected_pages)
            self.assertEqual(
                {
                    Path(path).relative_to(outputs / "DuplicatePaths").as_posix()
                    for path in controls.values()
                },
                {
                    "dependency/controls/Views/Admin/MainWindow.xaml.json",
                    "dependency/controls/Views/User/MainWindow.xaml.json",
                },
            )

            resource_ids = {
                item["source_id"] for item in resource_graph["resources"]
            }
            self.assertEqual(
                resource_ids,
                {"Assets/Admin/logo.svg", "Assets/User/logo.svg"},
            )
            self.assertEqual(
                len({(results / "public" / source_id) for source_id in resource_ids}),
                2,
            )

            target_paths = {
                target_relative_path(page_id, ".tsx").as_posix()
                for page_id in expected_pages
            }
            self.assertEqual(
                target_paths,
                {
                    "Views/Admin/MainWindow.tsx",
                    "Views/User/MainWindow.tsx",
                },
            )

            manifest = build_evaluation_manifest(
                "DuplicatePaths",
                output_base_dir=outputs,
                target_root=results,
                mapping_path=root / "missing-mapping.json",
            )
            self.assertEqual({page.page_id for page in manifest.pages}, expected_pages)
            self.assertEqual(
                len({component.component_id for component in manifest.components}),
                len(manifest.components),
            )

            (results / "Views" / "Admin").mkdir(parents=True)
            (results / "Views" / "Admin" / "MainWindow.tsx").write_text(
                "export function AdminMainWindow() { return <div />; }\n",
                encoding="utf-8",
            )
            (results / "MainWindow.tsx").write_text(
                "export function WrongMainWindow() { return <div />; }\n",
                encoding="utf-8",
            )
            manifest.compiler = CommandSpec(
                command=[
                    sys.executable,
                    "-c",
                    "raise SystemExit(0)",
                    "{entry}",
                ]
            )
            report = MigrationEvaluator(
                manifest,
                workspace_root=root,
            ).evaluate(method_id="IdentityFixture", run_id="offline")
            page_statuses = {
                item.page_id: item.status for item in report.page_results
            }
            self.assertEqual(
                page_statuses["Views/Admin/MainWindow.xaml"],
                PageEvaluationStatus.PAGE_COMPILE_PASSED,
            )
            self.assertEqual(
                page_statuses["Views/User/MainWindow.xaml"],
                PageEvaluationStatus.PAGE_MISSING,
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


class XamlSemanticTests(unittest.TestCase):
    SAMPLE = """\
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:local="clr-namespace:Fixture.Controls"
        x:Class="Fixture.MainWindow">
  <Window.Resources>
    <ResourceDictionary>
      <ResourceDictionary.MergedDictionaries>
        <ResourceDictionary Source="Themes/Colors.xaml" />
      </ResourceDictionary.MergedDictionaries>
      <DataTemplate x:Key="CardTemplate" DataType="{x:Type local:CardViewModel}">
        <local:Card />
      </DataTemplate>
    </ResourceDictionary>
  </Window.Resources>
  <StackPanel>
    <TextBox Text="{Binding Path=Name}" />
    <Button Command="{Binding SaveCommand}"
            CommandParameter="{Binding Id}"
            Click="Save_Click" />
    <TextBlock>
      <TextBlock.Text>
        <MultiBinding StringFormat="{}{0}-{1}" />
      </TextBlock.Text>
      <TextBlock.Tag>
        <PriorityBinding />
      </TextBlock.Tag>
    </TextBlock>
    <local:Widget />
  </StackPanel>
</Window>
"""

    def test_xaml_ir_structures_bindings_commands_events_and_custom_nodes(self) -> None:
        parser = XamlParser()
        parser.parse_string(self.SAMPLE)
        data = parser.to_dict()

        self.assertEqual(data["classification_summary"]["custom_control"], 2)
        self.assertEqual(data["semantic_reference_summary"]["binding"], 3)
        self.assertEqual(data["semantic_reference_summary"]["command"], 1)
        self.assertEqual(
            data["semantic_reference_summary"]["command_parameter"], 1
        )
        self.assertEqual(data["semantic_reference_summary"]["event_handler"], 1)
        self.assertEqual(data["semantic_reference_summary"]["multibinding"], 1)
        self.assertEqual(data["semantic_reference_summary"]["prioritybinding"], 1)
        self.assertEqual(data["semantic_reference_summary"]["file_resource"], 1)

        nodes = self._walk(data["root"])
        self.assertTrue(all(node["node_path"] for node in nodes))
        self.assertTrue(all(node["classification"] for node in nodes))
        self.assertTrue(
            any(
                detail["namespace"]
                == "http://schemas.microsoft.com/winfx/2006/xaml"
                and detail["name"] == "Class"
                for detail in data["root"]["attribute_details"]
            )
        )

    def test_nonsemantic_literal_and_resource_object_are_not_false_positives(self) -> None:
        parser = XamlParser()
        parser.parse_string(
            """
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
 xmlns:local="clr-namespace:Fixture.Converters">
  <local:NameConverter x:Key="Converter" />
  <TextBlock Text="literal" Click="{Binding NotAnEventHandler}" />
</ResourceDictionary>
"""
        )
        data = parser.to_dict()
        self.assertNotIn("event_handler", data["semantic_reference_summary"])
        self.assertEqual(data["semantic_reference_summary"]["binding"], 1)
        converter = next(
            node
            for node in self._walk(data["root"])
            if node["tag"] == "NameConverter"
        )
        self.assertEqual(converter["classification"], "resource_node")

    def test_xaml_semantic_ir_is_deterministic(self) -> None:
        first = XamlParser()
        second = XamlParser()
        first.parse_string(self.SAMPLE)
        second.parse_string(self.SAMPLE)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_control_dependency_preserves_nonbase_nodes_in_inventory(self) -> None:
        parser = XamlParser()
        parser.parse_string(self.SAMPLE)
        parser.source_id = "Views/MainWindow.xaml"
        parser.source_file = "repos/Synthetic/Views/MainWindow.xaml"
        parser.file_type = "page"
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "MainWindow.xaml.json"
            write_json(artifact, parser.to_dict())
            result = ControlDependencyAnalyzer(temp_dir).analyze_xaml_file(
                str(artifact)
            )

        self.assertEqual(
            result["node_inventory_count"],
            sum(result["node_classification_summary"].values()),
        )
        self.assertEqual(len(result["custom_controls"]), 2)
        self.assertTrue(
            all(
                item["retention"] == "separate_inventory"
                for item in result["custom_controls"]
            )
        )
        self.assertTrue(
            any(
                item["tag"] == "ResourceDictionary.MergedDictionaries"
                for item in result["node_inventory"]
            )
        )

    @staticmethod
    def _walk(root: dict) -> list[dict]:
        nodes = []
        stack = [root]
        while stack:
            node = stack.pop()
            nodes.append(node)
            stack.extend(reversed(node.get("children", [])))
        return nodes


class CsStructureCompletenessTests(unittest.TestCase):
    SAMPLE = """\
namespace Fixture.Models;

public partial record Person<T>(T Value) : Entity<T>
{
    private int first, second;
    public event EventHandler? Changed, Saved;
    public event EventHandler Explicit { add { } remove { } }
    public Dictionary<string, T?> Map<U>(List<U[]> input) => new();
}
"""

    def test_file_scoped_namespace_record_fields_events_and_generics_are_kept(self) -> None:
        parser = CsParser()
        parser.parse_string(self.SAMPLE)
        data = parser.to_dict()
        record = next(
            node for node in self._walk(data["root"]) if node["node_type"] == "record"
        )

        self.assertEqual(data["parse_status"], "complete")
        self.assertEqual(record["qualified_name"], "Fixture.Models.Person")
        self.assertEqual(record["modifiers"], ["public", "partial"])
        self.assertEqual(record["type_parameters"], ["T"])
        self.assertEqual(record["parameters"], [{"name": "Value", "type": "T"}])
        self.assertEqual(record["base_types"], ["Entity<T>"])
        self.assertEqual(
            [node["name"] for node in record["children"] if node["node_type"] == "field"],
            ["first", "second"],
        )
        self.assertEqual(
            [node["name"] for node in record["children"] if node["node_type"] == "event"],
            ["Changed", "Saved", "Explicit"],
        )
        method = next(
            node for node in record["children"] if node["node_type"] == "method"
        )
        self.assertEqual(method["return_type"], "Dictionary<string, T?>")
        self.assertEqual(method["type_parameters"], ["U"])
        self.assertEqual(method["parameters"][0]["type"], "List<U[]>")

    def test_tree_sitter_recovery_is_explicit_partial_status(self) -> None:
        parser = CsParser()
        parser.parse_string("namespace Broken; public class Demo { void Run( { }")
        data = parser.to_dict()

        self.assertEqual(data["parse_status"], "partial")
        self.assertGreater(data["tree_sitter_summary"]["error_nodes"], 0)
        self.assertTrue(data["diagnostics"])
        self.assertTrue(
            any(node["node_type"] == "class" for node in self._walk(data["root"]))
        )

    def test_conditional_compilation_members_are_preserved_with_evidence(self) -> None:
        parser = CsParser()
        parser.parse_string(
            """\
public class Conditional
{
#if DEBUG
    private const string Mode = "debug";
#else
    private const string Mode = "release";
    private void ReleaseOnly() { }
#endif
}
"""
        )
        nodes = self._walk(parser.to_dict()["root"])
        modes = [
            node for node in nodes
            if node["node_type"] == "field" and node["name"] == "Mode"
        ]
        release = next(
            node for node in nodes
            if node["node_type"] == "method" and node["name"] == "ReleaseOnly"
        )

        self.assertEqual(len(modes), 2)
        self.assertEqual(modes[0]["preprocessor_context"], ["#if DEBUG"])
        self.assertEqual(
            modes[1]["preprocessor_context"], ["#if DEBUG", "#else"]
        )
        self.assertEqual(
            release["preprocessor_context"], ["#if DEBUG", "#else"]
        )

    def test_csharp_structure_ir_is_deterministic(self) -> None:
        first = CsParser()
        second = CsParser()
        first.parse_string(self.SAMPLE)
        second.parse_string(self.SAMPLE)
        self.assertEqual(first.to_dict(), second.to_dict())

    @staticmethod
    def _walk(root: dict) -> list[dict]:
        nodes = []
        stack = [root]
        while stack:
            node = stack.pop()
            nodes.append(node)
            stack.extend(reversed(node.get("children", [])))
        return nodes


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

    def test_duplicate_types_are_candidates_and_partial_types_use_qualified_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            cs_root = output_root / "Synthetic" / "cs"
            sources = {
                "A/Shared.cs": "namespace A; public class Shared {}",
                "B/Shared.cs": "namespace B; public class Shared {}",
                "Consumer.cs": "public class Consumer { private Shared value; }",
                "Unique.cs": "public class Unique {}",
                "Resolved.cs": "public class Resolved { private Unique value; }",
                "Parts/One.cs": "namespace Demo; public partial class Combined {}",
                "Parts/Two.cs": "namespace Demo; public partial class Combined {}",
                "Negative.cs": "public class Negative { string Sharedness = \"x\"; }",
            }
            for source_id, source in sources.items():
                parser = CsParser()
                parser.parse_string(source)
                parser.source_id = source_id
                parser.source_file = f"repos/Synthetic/{source_id}"
                write_json(
                    mirrored_json_path(cs_root, source_id),
                    parser.to_dict(),
                )

            graph, _ = CsDependencyAnalyzer.analyze_project(
                "Synthetic", str(output_root)
            )
            repeated, _ = CsDependencyAnalyzer.analyze_project(
                "Synthetic", str(output_root)
            )

            self.assertEqual(graph, repeated)
            self.assertEqual(graph["files"]["Consumer.cs"]["dependencies"], [])
            self.assertEqual(
                graph["candidate_dependencies"]["Consumer.cs"][0]["candidates"],
                ["A/Shared.cs", "B/Shared.cs"],
            )
            self.assertEqual(
                graph["candidate_dependencies"]["Consumer.cs"][0]["source_line"],
                1,
            )
            self.assertIn(
                "Shared value",
                graph["candidate_dependencies"]["Consumer.cs"][0]["evidence"],
            )
            self.assertEqual(
                graph["files"]["Resolved.cs"]["dependencies"],
                ["Unique.cs"],
            )
            self.assertEqual(
                graph["files"]["Resolved.cs"]["dependency_evidence"][0][
                    "target_source_id"
                ],
                "Unique.cs",
            )
            self.assertNotIn("Negative.cs", graph["candidate_dependencies"])
            self.assertEqual(
                graph["partial_groups"],
                [
                    {
                        "qualified_name": "Demo.Combined",
                        "source_ids": ["Parts/One.cs", "Parts/Two.cs"],
                    }
                ],
            )


class PageDependencyCandidateTests(unittest.TestCase):
    def test_mvvm_datatemplate_prism_and_mvvmcross_candidates_keep_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "repos" / "NavigationFixture"
            output_root = root / "outputs"
            (project / "Views").mkdir(parents=True)
            (project / "ViewModels").mkdir()
            (project / "Views" / "Shell.xaml").write_text(
                """<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
 x:Class="Fixture.Views.Shell"><Grid /></Window>""",
                encoding="utf-8",
            )
            (project / "Views" / "Shell.xaml.cs").write_text(
                "namespace Fixture.Views; public partial class Shell { "
                "void Open() { _ = new DetailView(); } }",
                encoding="utf-8",
            )
            (project / "Views" / "DetailView.xaml").write_text(
                """<UserControl xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
 x:Class="Fixture.Views.DetailView"><TextBlock /></UserControl>""",
                encoding="utf-8",
            )
            (project / "Views" / "DetailView.xaml.cs").write_text(
                "namespace Fixture.Views; public partial class DetailView { }",
                encoding="utf-8",
            )
            (project / "ViewModels" / "ShellViewModel.cs").write_text(
                """namespace Fixture.ViewModels;
public class ShellViewModel {
  public ICommand OpenCommand { get; }
  void Open() {
    navigation.Navigate<DetailViewModel>();
    regionManager.RequestNavigate("MainRegion", "DetailView");
  }
  int NavigateCount => 0;
}""",
                encoding="utf-8",
            )
            (project / "App.xaml").write_text(
                """<Application xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
 xmlns:vm="clr-namespace:Fixture.ViewModels"
 xmlns:views="clr-namespace:Fixture.Views">
 <Application.Resources>
  <DataTemplate DataType="{x:Type vm:DetailViewModel}"><views:DetailView /></DataTemplate>
 </Application.Resources>
</Application>""",
                encoding="utf-8",
            )

            CsParser.parse_project(str(project), str(output_root))
            XamlParser.parse_project(str(project), str(output_root))
            first, _ = PageDependencyAnalyzer.analyze_project(
                "NavigationFixture", str(output_root)
            )
            second, _ = PageDependencyAnalyzer.analyze_project(
                "NavigationFixture", str(output_root)
            )

            self.assertEqual(first, second)
            self.assertEqual(
                first["pages"]["Views/Shell.xaml"]["dependencies"],
                ["Views/DetailView.xaml"],
            )
            certain_evidence = first["pages"]["Views/Shell.xaml"][
                "dependency_evidence"
            ]
            self.assertEqual(len(certain_evidence), 1)
            self.assertEqual(
                certain_evidence[0]["target_page_id"],
                "Views/DetailView.xaml",
            )
            self.assertIn("new DetailView", certain_evidence[0]["evidence"])
            mechanisms = {item["mechanism"] for item in first["candidate_edges"]}
            self.assertIn("mvvm-datatemplate-view-mapping", mechanisms)
            self.assertIn("mvvmcross-navigation", mechanisms)
            self.assertIn("prism-navigation", mechanisms)
            self.assertIn("command-navigation", mechanisms)
            self.assertTrue(
                all(item.get("evidence") for item in first["candidate_edges"])
            )
            self.assertFalse(
                any(
                    item.get("target_symbol") == "NavigateCount"
                    for item in first["candidate_edges"]
                )
            )


class ResourceDependencyTests(unittest.TestCase):
    def test_missing_project_file_produces_explicit_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = ResourceDependencyAnalyzer(temp_dir)
            result = analyzer.analyze_project_resources("NoProject")

            self.assertTrue(result["project_file_missing"])
            self.assertEqual(result["csproj_files"], [])
            self.assertEqual(result["resources"], [])

    def test_missing_csproj_uses_xaml_and_repository_resource_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "repos" / "MissingProject"
            outputs = root / "outputs"
            shutil.copytree(MISSING_CSPROJ_FIXTURE_ROOT, project)
            XamlParser.parse_project(str(project), str(outputs))

            first, _ = ResourceDependencyAnalyzer.analyze_project(
                "MissingProject", str(project), str(outputs)
            )
            second, _ = ResourceDependencyAnalyzer.analyze_project(
                "MissingProject", str(project), str(outputs)
            )

            self.assertEqual(first, second)
            self.assertTrue(first["project_file_missing"])
            self.assertEqual(first["csproj_files"], [])
            self.assertEqual(
                {resource["source_id"] for resource in first["resources"]},
                {"Assets/logo.png", "Fonts/App.ttf"},
            )
            self.assertTrue(
                all(
                    resource["discovery_sources"] == ["repository_scan"]
                    and not resource["declared_in_project"]
                    for resource in first["resources"]
                )
            )
            classifications = Counter(
                reference["classification"] for reference in first["references"]
            )
            self.assertEqual(classifications["internal_undeclared_file"], 3)
            self.assertEqual(classifications["missing_target"], 1)
            self.assertEqual(
                first["summary"]["closure"]["unexplained_reference_count"], 0
            )

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
