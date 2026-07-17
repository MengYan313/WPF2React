# -*- coding: utf-8 -*-
"""使用纯合成页面验证无资源/模板/数据时的页面组装轮次。"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration.page_assembly_agent import PageAssemblyAgent


SYNTHETIC_PAGE = """\
<Window Title="Synthetic Smoke">
  <Button Content="Confirm" />
</Window>
"""

SYNTHETIC_ROOT = """\
import Button from '@mui/material/Button';

export function RootSmoke() {
  return <Button variant="contained">Confirm</Button>;
}
"""


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.marker_mode()
    original_cwd = Path.cwd()

    with tempfile.TemporaryDirectory(prefix="wpf2react-page-smoke-") as temp_dir:
        temp_path = Path(temp_dir)
        os.chdir(temp_path)
        try:
            agent = PageAssemblyAgent(
                project_name="SyntheticSmoke",
                output_base_dir=str(temp_path / "outputs"),
                llm_config=config,
            )
            try:
                result = await agent._assemble_page(
                    page_name="SmokePage",
                    page_source=SYNTHETIC_PAGE,
                    root_result={
                        "react_code": SYNTHETIC_ROOT,
                        "imports": ["import Button from '@mui/material/Button';"],
                        "interfaces": "",
                    },
                    page_layout_description="A single centered confirmation action.",
                    child_page_references="No child pages are referenced in this page.",
                    direct_dependencies=[],
                    template="",
                    data={},
                )
            finally:
                if agent.llm_client:
                    await agent.llm_client.close()
        finally:
            os.chdir(original_cwd)

        page_code = result.get("page_code", "")
        page_named = "SmokePage" in page_code
        no_grid = "<Grid" not in page_code
        success = bool(page_code) and page_named and no_grid
        print(f"model={config.model}")
        print(f"page_nonempty={bool(page_code)}")
        print(f"page_name_present={page_named}")
        print(f"grid_absent={no_grid}")
        return success


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
