"""三条迁移 baseline 的确定性离线契约测试。"""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from src.llm import LLMConfig
from src.migration.baselines.common import (
    METHOD_LLM_DIRECT,
    METHOD_NO_RAG,
    METHOD_RULETRANS,
    BaselineRunPaths,
    copy_parser_outputs,
    safe_generated_path,
    write_generated_files,
)
from src.migration.baselines.llm_direct import LLMDirectBudgetRunner
from src.migration.baselines.ruletrans import RuleTransMUIRunner
from src.migration.base import BaseMigrationAgent
from src.migration.messages import MUISelectionRequest
from src.migration.mui_select_agent import MUISelectAgent


_XAML_NAMESPACE = "http://schemas.microsoft.com/winfx/2006/xaml/presentation"
_X_NAMESPACE = "http://schemas.microsoft.com/winfx/2006/xaml"


class BaselineOfflineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory(prefix="wpf2react-baselines-")
        self.workspace = Path(self.temp_context.name)
        self.source_base = self.workspace / "repos"
        self.result_base = self.workspace / "results"
        self.artifact_base = self.workspace / "outputs" / "baselines"
        self.project_id = "Synthetic"
        self.source_root = self.source_base / self.project_id
        self.source_root.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def _paths(self, method_id: str, run_id: str) -> BaselineRunPaths:
        return BaselineRunPaths.build(
            method_id,
            run_id,
            self.project_id,
            source_base_dir=self.source_base,
            result_base_dir=self.result_base,
            artifact_base_dir=self.artifact_base,
        )

    def _write_ruletrans_page(self) -> None:
        (self.source_root / "MainWindow.xaml").write_text(
            f"""<Window xmlns=\"{_XAML_NAMESPACE}\"
    xmlns:x=\"{_X_NAMESPACE}\"
    xmlns:local=\"clr-namespace:Synthetic\"
    x:Class=\"Synthetic.MainWindow\">
  <Grid Width=\"320\" Visibility=\"Collapsed\">
    <Button Click=\"OnClose\">
      <Button.ToolTip>说明文字</Button.ToolTip>
      _Close
    </Button>
    <local:ChartControl />
  </Grid>
</Window>
""",
            encoding="utf-8",
        )

    def test_ruletrans_is_deterministic_and_marks_unknown_controls(self) -> None:
        self._write_ruletrans_page()
        first_paths = self._paths(METHOD_RULETRANS, "run-a")
        second_paths = self._paths(METHOD_RULETRANS, "run-b")

        first = RuleTransMUIRunner(first_paths).run()
        second = RuleTransMUIRunner(second_paths).run()
        first_code = (first_paths.result_root / "MainWindow.tsx").read_text(
            encoding="utf-8"
        )
        second_code = (second_paths.result_root / "MainWindow.tsx").read_text(
            encoding="utf-8"
        )

        self.assertEqual(first["status"], "success")
        self.assertEqual(first["llm_calls"], 0)
        self.assertEqual(first["unsupported_control_count"], 1)
        self.assertEqual(first_code, second_code)
        self.assertNotIn("<Grid", first_code)
        self.assertIn("Close", first_code)
        self.assertNotIn("说明文字", first_code)
        self.assertIn('data-unsupported-wpf={"ChartControl"}', first_code)
        self.assertEqual(first_code.count("sx="), 1)
        self.assertIn('"display": "none"', first_code)
        self.assertEqual(second["page_count"], 1)

    def test_ruletrans_recovers_explicit_dialog_open_and_close(self) -> None:
        (self.source_root / "MainWindow.xaml").write_text(
            f"""<Window xmlns=\"{_XAML_NAMESPACE}\" xmlns:x=\"{_X_NAMESPACE}\"
    x:Class=\"Synthetic.MainWindow\"><Button Click=\"OpenChild\">Open</Button></Window>""",
            encoding="utf-8",
        )
        (self.source_root / "MainWindow.cs").write_text(
            """public partial class MainWindow {
private void OpenChild(object sender, object args) {
  var dialog = new ChildWindow();
  dialog.ShowDialog();
}
}
""",
            encoding="utf-8",
        )
        (self.source_root / "ChildWindow.xaml").write_text(
            f"""<Window xmlns=\"{_XAML_NAMESPACE}\" xmlns:x=\"{_X_NAMESPACE}\"
    x:Class=\"Synthetic.ChildWindow\"><Button Click=\"CloseChild\">Close</Button></Window>""",
            encoding="utf-8",
        )
        (self.source_root / "ChildWindow.cs").write_text(
            """public partial class ChildWindow {
private void CloseChild(object sender, object args) { Close(); }
}
""",
            encoding="utf-8",
        )
        paths = self._paths(METHOD_RULETRANS, "navigation")

        summary = RuleTransMUIRunner(paths).run()
        main_code = (paths.result_root / "MainWindow.tsx").read_text(encoding="utf-8")
        child_code = (paths.result_root / "ChildWindow.tsx").read_text(encoding="utf-8")
        app_code = (paths.result_root / "App.tsx").read_text(encoding="utf-8")

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["entry_page"], "MainWindow")
        self.assertIn("import { useState } from 'react';", main_code)
        self.assertIn("setChildWindowOpen(true)", main_code)
        self.assertIn('data-navigation-target={"ChildWindow"}', main_code)
        self.assertIn("<ChildWindow open={childWindowOpen}", main_code)
        self.assertIn("onClick={onClose}", child_code)
        self.assertIn("return <MainWindow />", app_code)

    async def test_llm_direct_uses_mechanical_raw_package_and_budget(self) -> None:
        (self.source_root / "MainWindow.xaml").write_text(
            f"""<Window xmlns=\"{_XAML_NAMESPACE}\"><Button>Go</Button></Window>""",
            encoding="utf-8",
        )
        (self.source_root / "MainWindow.cs").write_text(
            "public partial class MainWindow { void Go() {} }\n",
            encoding="utf-8",
        )
        (self.source_root / "Helper.cs").write_text(
            "public static class Helper {}\n",
            encoding="utf-8",
        )
        (self.source_root / "App.xaml").write_text(
            f"<Application xmlns=\"{_XAML_NAMESPACE}\" />\n",
            encoding="utf-8",
        )
        seen_prompts: list[str] = []

        async def fake_completion(
            system_prompt: str,
            user_prompt: str,
            schema: Mapping[str, Any],
            max_tokens: int,
        ) -> dict[str, Any]:
            self.assertIn("原始文件", user_prompt)
            self.assertIn("MainWindow.xaml", user_prompt)
            self.assertIn("MainWindow.cs", user_prompt)
            self.assertIn("Helper.cs", user_prompt)
            self.assertNotIn("control_MainWindow.json", user_prompt)
            self.assertIn("files", schema["required"])
            self.assertGreater(max_tokens, 0)
            seen_prompts.append(system_prompt + user_prompt)
            return {
                "files": [
                    {
                        "path": "MainWindow.tsx",
                        "content": (
                            "import { Button } from '@mui/material';\n"
                            "export function MainWindow() { return <Button>Go</Button>; }\n"
                            "export default MainWindow;\n"
                        ),
                    }
                ],
                "unresolved_items": [],
            }

        paths = self._paths(METHOD_LLM_DIRECT, "offline")
        summary = await LLMDirectBudgetRunner(
            paths,
            completion=fake_completion,
            model_name="offline-model",
            total_token_budget=50_000,
            max_input_tokens_per_call=10_000,
            max_output_tokens_per_call=2_000,
        ).run(merge_project=False)

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["page_count"], 1)
        self.assertEqual(summary["llm_logical_calls"], 1)
        self.assertEqual(summary["provider_call_upper_bound"], 2)
        self.assertEqual(summary["project_merge_status"], "not_requested")
        self.assertEqual(len(seen_prompts), 1)
        self.assertTrue((paths.result_root / "MainWindow.tsx").is_file())
        packages = json.loads(
            (paths.artifact_root / "package_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            packages[0]["included_files"],
            ["MainWindow.xaml", "MainWindow.cs", "Helper.cs"],
        )

    async def test_llm_direct_counts_optional_merge_separately_from_pages(self) -> None:
        for page_id in ("MainWindow", "ChildWindow"):
            (self.source_root / f"{page_id}.xaml").write_text(
                f"<Window xmlns=\"{_XAML_NAMESPACE}\"><Button>{page_id}</Button></Window>",
                encoding="utf-8",
            )

        async def fake_completion(
            system_prompt: str,
            user_prompt: str,
            schema: Mapping[str, Any],
            max_tokens: int,
        ) -> dict[str, Any]:
            del system_prompt, schema, max_tokens
            if "工程级机械合并" in user_prompt:
                return {
                    "files": [
                        {
                            "path": "App.tsx",
                            "content": "export function App() { return <div />; }\nexport default App;\n",
                        }
                    ],
                    "unresolved_items": [],
                }
            if "机械页面包 ChildWindow" in user_prompt:
                return {
                    "files": [
                        {
                            "path": "ChildWindow.tsx",
                            "content": (
                                "import { Dialog } from '@mui/material';\n"
                                "export interface ChildWindowProps {\n"
                                "  open: boolean;\n"
                                "  onClose: () => void;\n"
                                "}\n"
                                "export function ChildWindow({ open, onClose }: ChildWindowProps) {\n"
                                "  return <Dialog open={open} onClose={onClose} />;\n}\n"
                                "export default ChildWindow;\n"
                            ),
                        }
                    ],
                    "unresolved_items": [],
                }
            return {
                "files": [
                    {
                        "path": "MainWindow.tsx",
                        "content": (
                            "export function MainWindow() { return <div />; }\n"
                            "export default MainWindow;\n"
                        ),
                    }
                ],
                "unresolved_items": [],
            }

        paths = self._paths(METHOD_LLM_DIRECT, "merge")
        summary = await LLMDirectBudgetRunner(
            paths,
            completion=fake_completion,
            total_token_budget=80_000,
            max_input_tokens_per_call=10_000,
            max_output_tokens_per_call=2_000,
        ).run(merge_project=True)

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["page_count"], 2)
        self.assertEqual(summary["successful_pages"], 2)
        self.assertEqual(summary["project_merge_status"], "success")
        self.assertEqual(summary["llm_logical_calls"], 3)
        records = (paths.artifact_root / "generation_records.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(records), 3)

    async def test_no_rag_keeps_name_mapping_but_never_injects_docs(self) -> None:
        mapping_path = self.workspace / "mapping.json"
        mapping_path.write_text(
            json.dumps(
                {
                    "Button": {
                        "mui_component": "Button",
                        "usage_example": "SECRET_RAG_DOCUMENT",
                        "notes": "SECRET_RAG_NOTES",
                    }
                }
            ),
            encoding="utf-8",
        )
        agent = MUISelectAgent(
            mui_json_path=str(self.workspace / "must-not-be-read.json"),
            wpf_to_mui_mapping_path=str(mapping_path),
            llm_config=LLMConfig.json_mode_config(),
            retrieval_enabled=False,
            use_semantic_similarity=True,
        )

        mapped = await agent.handle_selection_request(
            MUISelectionRequest(wpf_source="<Button />", wpf_tag="Button"),
            None,
        )
        unknown = await agent.handle_selection_request(
            MUISelectionRequest(wpf_source="<CustomChart />", wpf_tag="CustomChart"),
            None,
        )

        self.assertFalse(agent.retrieval_enabled)
        self.assertFalse(agent.use_semantic_similarity)
        self.assertEqual(agent.mui_components_index, {})
        self.assertEqual(mapped.selected_components, ["Button"])
        self.assertEqual(mapped.docs, [""])
        self.assertEqual(unknown.selected_components, [])
        self.assertEqual(unknown.docs, [])
        await agent.close_llm()

    async def test_migration_agent_usage_counts_json_repair_provider_call(self) -> None:
        class FakeResponse:
            def __init__(self, content: str) -> None:
                self.content = content

        class FakeModelClient:
            def __init__(self) -> None:
                self.responses = ["invalid", '{"answer": "fixed"}']

            async def create(self, *args: Any, **kwargs: Any) -> FakeResponse:
                del args, kwargs
                return FakeResponse(self.responses.pop(0))

            def actual_usage(self) -> SimpleNamespace:
                return SimpleNamespace(prompt_tokens=11, completion_tokens=7)

        agent = object.__new__(BaseMigrationAgent)
        agent.llm_client = SimpleNamespace(
            model_client=FakeModelClient(),
            config=SimpleNamespace(max_tokens=128),
        )
        agent.logger = logging.getLogger("baseline-usage-test")
        agent.logical_llm_calls = 0
        agent.provider_llm_calls = 0
        result = await agent.call_json(
            "system",
            "user",
            {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(result, {"answer": "fixed"})
        self.assertEqual(
            agent.llm_usage_snapshot(),
            {
                "logical_calls": 1,
                "provider_calls": 2,
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        )

    def test_run_paths_and_generated_paths_are_isolated(self) -> None:
        paths = self._paths(METHOD_RULETRANS, "immutable")
        paths.prepare()
        (paths.result_root / "evidence.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            paths.prepare()
        with self.assertRaises(ValueError):
            safe_generated_path(paths.result_root, "../outside.tsx")
        with self.assertRaises(ValueError):
            safe_generated_path(paths.result_root, "node_modules/evil.ts")

    def test_generated_file_batch_is_prevalidated_before_any_write(self) -> None:
        target = self.workspace / "atomic-target"
        target.mkdir()
        with self.assertRaises(ValueError):
            write_generated_files(
                target,
                [
                    {"path": "Good.tsx", "content": "export const good = true;\n"},
                    {"path": "unresolved_items", "content": ""},
                ],
            )
        self.assertFalse((target / "Good.tsx").exists())

    def test_no_rag_parser_copy_excludes_previous_migration_artifacts(self) -> None:
        parser_base = self.workspace / "parser-outputs"
        project_output = parser_base / self.project_id
        (project_output / "dependency").mkdir(parents=True)
        (project_output / "dependency" / "page_dependency.json").write_text(
            "{}\n", encoding="utf-8"
        )
        (project_output / "migration").mkdir()
        (project_output / "migration" / "contaminated.json").write_text(
            "{}\n", encoding="utf-8"
        )

        isolated_base = copy_parser_outputs(
            self.project_id,
            self.workspace / "artifact",
            parser_output_base_dir=parser_base,
        )

        self.assertTrue(
            (isolated_base / self.project_id / "dependency" / "page_dependency.json").is_file()
        )
        self.assertFalse((isolated_base / self.project_id / "migration").exists())


if __name__ == "__main__":
    unittest.main()
