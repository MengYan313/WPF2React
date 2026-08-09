"""三仓全量实验暴露的确定性流程回归测试。"""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

from src.migration.cs_migrate_agent import CsMigrateAgent
from src.migration.data_migrate_agent import DataMigrateAgent
from src.migration.evaluation.matcher import DeterministicComponentJudge
from src.migration.evaluation.models import ComponentSpec, MatchStatus
from src.migration.page_assembly_agent import PageAssemblyAgent


class PipelineRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_cs_graph_is_a_successful_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dependency_file = root / "cs_dependency.json"
            dependency_file.write_text(
                json.dumps({"migration_order": [], "files": {}, "total_files": 0}),
                encoding="utf-8",
            )
            agent = object.__new__(CsMigrateAgent)
            agent.logger = logging.getLogger(__name__)

            result = await agent._migrate_batch_cs_files(
                project_name="Empty",
                cs_dependency_file=str(dependency_file),
                output_dir=str(root / "result"),
                ts_info_file=str(root / "ts_info.json"),
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["files_migrated"], 0)
            self.assertEqual(result["files_failed"], 0)

    async def test_page_contract_uses_repository_relative_page_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dependency_dir = Path(temp_dir)
            (dependency_dir / "page_dependency.json").write_text(
                json.dumps(
                    {
                        "pages": {
                            "Views/Main.xaml": {"depended_by_count": 0},
                        }
                    }
                ),
                encoding="utf-8",
            )
            agent = object.__new__(PageAssemblyAgent)
            agent.dependency_dir = dependency_dir
            agent.logger = logging.getLogger(__name__)
            system_prompts = []

            async def capture_prompt(system_message: str, user_message: str) -> str:
                system_prompts.append(system_message)
                return user_message

            agent.request_typescript_code = capture_prompt
            await agent._assemble_round_1_initial(
                "Views/Main.xaml",
                "Views__Main",
                "export function Views__Main() { return null; }",
            )
            temp_tsx = dependency_dir / "Views__Main_temp.tsx"
            temp_tsx.write_text(
                "export function Views__Main({ action }: Props) { return null; }",
                encoding="utf-8",
            )
            await agent._assemble_round_7_code_style(
                "Views__Main",
                True,
                [],
                temp_tsx,
            )

            self.assertEqual(len(system_prompts), 2)
            self.assertTrue(
                all("不得声明或接收 Props" in prompt for prompt in system_prompts)
            )

    def test_data_types_follow_repository_relative_source_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            ts_file = output_dir / "ViewModels" / "MainViewModel.ts"
            ts_file.parent.mkdir()
            ts_file.write_text("export class MainViewModel {}", encoding="utf-8")
            class_info = {
                "class_name": "MainViewModel",
                "source_id": "ViewModels/MainViewModel.cs",
            }
            agent = object.__new__(DataMigrateAgent)

            self.assertEqual(
                agent._read_typescript_file_content(class_info, output_dir),
                "export class MainViewModel {}",
            )
            self.assertEqual(
                agent._typescript_import(class_info, output_dir),
                "import { MainViewModel } from './ViewModels/MainViewModel';",
            )

    def test_component_judge_ignores_failed_temp_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target_root = Path(temp_dir)
            (target_root / "Page_temp.tsx").write_text(
                "export function Page() { return <Box />; }",
                encoding="utf-8",
            )
            component = ComponentSpec(
                component_id="Page.xaml:/Grid[1]",
                page_id="Page.xaml",
                source_file="repos/Page.xaml",
                source_node_path="/Grid[1]",
                source_tag="Grid",
                source_name="Page",
                target_file_hints=["Page.tsx"],
                target_tag_hints=["Box"],
            )

            match = DeterministicComponentJudge().judge([component], target_root)[0]

            self.assertEqual(match.status, MatchStatus.NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
