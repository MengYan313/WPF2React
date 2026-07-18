"""LLM-Direct-Budget 单页面、单逻辑调用真实 LLM smoke。"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration.baselines.common import METHOD_LLM_DIRECT, BaselineRunPaths
from src.migration.baselines.llm_direct import LLMDirectBudgetRunner


SYNTHETIC_XAML = """\
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        x:Class="SyntheticDirect.MainWindow"
        Title="Direct Smoke">
  <StackPanel>
    <TextBlock Text="Direct baseline smoke" />
    <Button Content="Confirm" Click="OnConfirm" />
  </StackPanel>
</Window>
"""

SYNTHETIC_CS = """\
namespace SyntheticDirect;
public partial class MainWindow
{
    private void OnConfirm(object sender, object args) { }
}
"""


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.json_mode_config()
    with tempfile.TemporaryDirectory(prefix="wpf2react-direct-baseline-") as temp_dir:
        workspace = Path(temp_dir)
        project_id = "SyntheticDirect"
        source_root = workspace / "repos" / project_id
        source_root.mkdir(parents=True)
        (source_root / "MainWindow.xaml").write_text(SYNTHETIC_XAML, encoding="utf-8")
        (source_root / "MainWindow.cs").write_text(SYNTHETIC_CS, encoding="utf-8")
        paths = BaselineRunPaths.build(
            METHOD_LLM_DIRECT,
            "smoke",
            project_id,
            source_base_dir=workspace / "repos",
            result_base_dir=workspace / "results" / "baselines",
            artifact_base_dir=workspace / "outputs" / "baselines",
        )
        summary = await LLMDirectBudgetRunner(
            paths,
            llm_config=config,
            total_token_budget=24_000,
            max_input_tokens_per_call=8_000,
            max_output_tokens_per_call=3_000,
        ).run(page_names=["MainWindow"], merge_project=False)
        generated_pages = list(paths.result_root.rglob("MainWindow.tsx"))
        content = (
            generated_pages[0].read_text(encoding="utf-8") if generated_pages else ""
        )
        success = (
            summary.get("status") == "success"
            and summary.get("page_count") == 1
            and summary.get("llm_logical_calls") == 1
            and (summary.get("provider_actual_calls") or 0) > 0
            and (summary.get("provider_total_tokens") or 0) > 0
            and bool(content)
            and "<Grid" not in content
        )
        print(f"model={config.model}")
        print(f"status={summary.get('status')}")
        print(f"logical_calls={summary.get('llm_logical_calls')}")
        print(f"provider_calls={summary.get('provider_actual_calls')}")
        print(f"provider_total_tokens={summary.get('provider_total_tokens')}")
        print(f"generated_page={bool(generated_pages)}")
        print(f"grid_absent={'<Grid' not in content}")
        return success


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
