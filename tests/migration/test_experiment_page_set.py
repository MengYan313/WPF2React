"""冻结实验页面集合的离线读取测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.migration.experiment_page_set import load_project_page_selection


class ExperimentPageSetTests(unittest.TestCase):
    def test_loads_project_pages_and_manual_edges(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "page-set.json"
            path.write_text(
                json.dumps(
                    {
                        "selection_id": "selection-v1",
                        "id_scheme": "repository-relative-posix-v1",
                        "projects": [
                            {
                                "project": "Demo",
                                "pages": ["Views/Main.xaml", "Views/Dialog.xaml"],
                                "manual_edges": [
                                    {
                                        "source": "Views/Main.xaml",
                                        "target": "Views/Dialog.xaml",
                                        "relation": "dialog_navigation",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            selection = load_project_page_selection(path, "Demo")

            self.assertEqual(selection.selection_id, "selection-v1")
            self.assertEqual(selection.page_ids, ("Views/Main.xaml", "Views/Dialog.xaml"))
            self.assertEqual(selection.manual_edges[0]["relation"], "dialog_navigation")

    def test_resolves_incremental_page_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "v1.json").write_text(
                json.dumps(
                    {
                        "selection_id": "v1",
                        "id_scheme": "repository-relative-posix-v1",
                        "selection_policy": {"simple_page_control_limit": 10},
                        "projects": [
                            {
                                "project": "Demo",
                                "rationale": "基础页。",
                                "boundary_note": "仅基础页。",
                                "pages": ["Views/Main.xaml"],
                                "manual_edges": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "v2.json").write_text(
                json.dumps(
                    {
                        "selection_id": "v2",
                        "id_scheme": "repository-relative-posix-v1",
                        "extends": "v1.json",
                        "selection_policy_overrides": {
                            "maximum_standalone_page_ratio": 0.3
                        },
                        "project_updates": [
                            {
                                "project": "Demo",
                                "add_pages": ["Views/Dialog.xaml"],
                                "add_manual_edges": [
                                    {
                                        "source": "Views/Main.xaml",
                                        "target": "Views/Dialog.xaml",
                                        "relation": "dialog_navigation",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            selection = load_project_page_selection(root / "v2.json", "Demo")

            self.assertEqual(selection.selection_id, "v2")
            self.assertEqual(selection.page_ids, ("Views/Main.xaml", "Views/Dialog.xaml"))
            self.assertEqual(len(selection.manual_edges), 1)


if __name__ == "__main__":
    unittest.main()
