"""迁移编排和 Runtime 生命周期的离线测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from src.migration.migration_orchestrator import MigrationOrchestrator
from src.migration.migration_team import MigrationTeam


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.orchestrator = MigrationOrchestrator(
            "Synthetic",
            output_base_dir=str(self.root / "outputs"),
            result_dir=str(self.root / "results"),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dependency_graph_is_strict_and_page_filter_keeps_graph_order(self) -> None:
        dependency_file = self.orchestrator.dependency_file
        dependency_file.parent.mkdir(parents=True)
        graph = {
            "migration_order": ["Views/A.xaml", "Views/B.xaml"],
            "pages": {
                "Views/A.xaml": {
                    "page_id": "Views/A.xaml",
                    "component_name": "ViewsA",
                    "control_file": "dependency/controls/Views/A.xaml.json",
                },
                "Views/B.xaml": {
                    "page_id": "Views/B.xaml",
                    "component_name": "ViewsB",
                    "control_file": "dependency/controls/Views/B.xaml.json",
                },
            },
        }
        dependency_file.write_text(json.dumps(graph), encoding="utf-8")

        loaded = self.orchestrator.load_dependency_graph()
        self.assertEqual(
            self.orchestrator._select_pages(
                loaded,
                ["Views/B.xaml", "Views/A.xaml", "Views/B.xaml"],
            ),
            ["Views/A.xaml", "Views/B.xaml"],
        )

        graph["migration_order"].append("Views/Missing.xaml")
        dependency_file.write_text(json.dumps(graph), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "不在 pages"):
            self.orchestrator.load_dependency_graph()


class OrchestratorFailureBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_failure_is_recorded_without_hiding_the_exception_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            orchestrator = MigrationOrchestrator(
                "Synthetic",
                output_base_dir=str(root / "outputs"),
                result_dir=str(root / "results"),
            )

            class FailingTeam:
                async def migrate_page(self, **kwargs):
                    raise RuntimeError("provider unavailable")

            orchestrator.migration_team = FailingTeam()
            result = await orchestrator._migrate_page(
                1,
                1,
                "Views/Main.xaml",
                {
                    "component_name": "ViewsMain",
                    "control_file": "dependency/controls/Views/Main.xaml.json",
                    "dependencies": [],
                },
                [],
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error"], "provider unavailable")
            self.assertEqual(orchestrator.migration_results, [result])


class RuntimeLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_close_collects_usage_once(self) -> None:
        events = []

        class Runtime:
            async def stop_when_idle(self):
                events.append("stop")

            async def close(self):
                events.append("close")

        class Agent:
            def llm_usage_snapshot(self):
                return {
                    "logical_calls": 1,
                    "provider_calls": 2,
                    "prompt_tokens": 3,
                    "completion_tokens": 4,
                    "total_tokens": 7,
                }

        team = object.__new__(MigrationTeam)
        runtime = Runtime()
        team.runtime = runtime
        team._active_runtime_agents = [Agent()]
        team._llm_usage = {
            "logical_calls": 0,
            "provider_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        await team._close_runtime(runtime)

        self.assertEqual(events, ["stop", "close"])
        self.assertIsNone(team.runtime)
        self.assertEqual(team.get_llm_usage()["provider_calls"], 2)


if __name__ == "__main__":
    unittest.main()
