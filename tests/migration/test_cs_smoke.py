"""使用纯合成 C# 输入验证 C#→TypeScript 迁移和分析链路。"""

import asyncio
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration.cs_migrate_agent import CsMigrateAgent


SYNTHETIC_CSHARP = """\
namespace SyntheticSmoke;

public sealed class SmokeCounter
{
    public int Value { get; set; }

    public void Increment()
    {
        Value += 1;
    }
}
"""


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.json_mode_config()

    with tempfile.TemporaryDirectory(prefix="wpf2react-cs-smoke-") as temp_dir:
        temp_path = Path(temp_dir)
        source_file = temp_path / "SmokeCounter.cs"
        output_dir = temp_path / "outputs"
        source_file.write_text(SYNTHETIC_CSHARP, encoding="utf-8")

        agent = CsMigrateAgent(
            project_name="SyntheticSmoke",
            output_base_dir=str(output_dir),
            llm_config=config,
        )
        try:
            result = await agent._migrate_single_cs_file(
                file_name="SmokeCounter",
                cs_file_path=str(source_file),
                dependencies=[],
                defined_types=["SmokeCounter"],
                output_dir=str(output_dir),
                ts_info_file=str(output_dir / "ts_info.json"),
                dependency_contents={},
            )
        finally:
            if agent.llm_client:
                await agent.llm_client.close()

        output_file = Path(result.get("output_file", ""))
        content = output_file.read_text(encoding="utf-8") if output_file.is_file() else ""
        success = bool(result.get("success")) and bool(content)

        print(f"model={config.model}")
        print(f"migration_success={bool(result.get('success'))}")
        print(f"output_nonempty={bool(content)}")
        return success


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
