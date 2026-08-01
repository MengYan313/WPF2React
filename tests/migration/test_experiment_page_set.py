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

            self.assertEqual(selection.page_ids, ("Views/Main.xaml", "Views/Dialog.xaml"))
            self.assertEqual(selection.manual_edges[0]["relation"], "dialog_navigation")


if __name__ == "__main__":
    unittest.main()
