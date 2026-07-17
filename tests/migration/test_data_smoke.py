# -*- coding: utf-8 -*-
"""使用纯合成 XAML 数据验证数据资源迁移链路。"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration import MigrationTeam


SYNTHETIC_DATA = {
    "project_name": "SyntheticSmoke",
    "total_data_resources": 1,
    "data_resources": [
        {
            "key": "SmokeItems",
            "tag": "x:Array",
            "source_code": (
                '<x:Array Type="sys:String">'
                '<sys:String>Alpha</sys:String>'
                '<sys:String>Beta</sys:String>'
                '</x:Array>'
            ),
        }
    ],
}


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.marker_mode()

    with tempfile.TemporaryDirectory(prefix="wpf2react-data-smoke-") as temp_dir:
        temp_path = Path(temp_dir)
        data_file = temp_path / "data_resources.json"
        output_file = temp_path / "data.ts"
        data_file.write_text(
            json.dumps(SYNTHETIC_DATA, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        team = MigrationTeam(
            project_name="SyntheticSmoke",
            output_base_dir=str(temp_path / "outputs"),
            data_migrate_llm_config=config,
        )
        result = await team.migrate_data(
            data_resources_file=str(data_file),
            output_file=str(output_file),
        )

        content = output_file.read_text(encoding="utf-8") if output_file.is_file() else ""
        marker_free = "[TypeScript Code]" not in content
        named_export = "smokeItems" in content
        success = bool(result.get("success")) and bool(content) and marker_free and named_export

        print(f"model={config.model}")
        print(f"migration_success={bool(result.get('success'))}")
        print(f"output_nonempty={bool(content)}")
        print(f"marker_free={marker_free}")
        print(f"expected_name_present={named_export}")
        return success


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
