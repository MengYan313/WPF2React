# -*- coding: utf-8 -*-
"""单控件合成页面的 PageMigrateAgent→PageAssemblyAgent 端到端 smoke。"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration import MigrationTeam


SYNTHETIC_CONTROL_DATA = {
    "source_file": "SyntheticSmoke/SmokePage.xaml",
    "xaml_json_file": "SyntheticSmoke/SmokePage.xaml.json",
    "namespaces": {},
    "control_count": 1,
    "root_info": {
        "tag": "Window",
        "source_code": (
            '<Window Title="Synthetic Smoke">'
            '<Button Content="Confirm" />'
            '</Window>'
        ),
        "attributes": {"Title": "Synthetic Smoke"},
        "template": "",
        "data": {},
    },
    "controls": {
        "tag": "Button",
        "source_code": '<Button Content="Confirm" />',
        "attributes": {"Content": "Confirm"},
        "template": "",
        "data": {},
        "children": [],
    },
}

SYNTHETIC_PAGE_DEPENDENCY = {
    "project_name": "SyntheticSmoke",
    "total_pages": 1,
    "pages": {
        "SmokePage": {
            "dependencies": [],
            "depended_by": [],
            "depended_by_count": 0,
            "cs_file": "",
        }
    },
    "migration_order": ["SmokePage"],
}


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.marker_mode()
    repo_root = Path(__file__).resolve().parents[2]
    original_cwd = Path.cwd()

    with tempfile.TemporaryDirectory(prefix="wpf2react-page-pipeline-") as temp_dir:
        temp_path = Path(temp_dir)
        dependency_dir = temp_path / "outputs" / "SyntheticSmoke" / "dependency"
        dependency_dir.mkdir(parents=True)
        control_file = dependency_dir / "control_SmokePage.json"
        control_file.write_text(
            json.dumps(SYNTHETIC_CONTROL_DATA, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (dependency_dir / "page_dependency.json").write_text(
            json.dumps(SYNTHETIC_PAGE_DEPENDENCY, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (temp_path / "rags").symlink_to(repo_root / "rags", target_is_directory=True)

        os.chdir(temp_path)
        try:
            team = MigrationTeam(
                project_name="SyntheticSmoke",
                output_base_dir=str(temp_path / "outputs"),
                mui_select_llm_config=config,
                component_migrate_llm_config=config,
                page_migrate_llm_config=config,
                page_assembly_llm_config=config,
            )
            result = await team.migrate_page(
                page_name="SmokePage",
                control_json_path=str(control_file),
                output_dir=str(temp_path / "results" / "SyntheticSmoke"),
            )

            output_path = Path(result.get("output_path", ""))
            if not output_path.is_absolute():
                output_path = temp_path / output_path
            content = output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
        finally:
            os.chdir(original_cwd)

        no_grid = "<Grid" not in content
        success = bool(result.get("success")) and bool(content) and no_grid
        print(f"model={config.model}")
        print(f"pipeline_success={bool(result.get('success'))}")
        print(f"components={result.get('migrated_components', 0)}/{result.get('total_components', 0)}")
        print(f"output_nonempty={bool(content)}")
        print(f"grid_absent={no_grid}")
        return success


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
