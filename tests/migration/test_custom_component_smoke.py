"""用真实低档模型验证自建控件检索后的组件迁移效果。"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration.component_migrate_agent import ComponentMigrateAgent
from src.migration.messages import ComponentMigrationRequest, MUISelectionRequest
from src.migration.mui_select_agent import MUISelectAgent
from src.parser.io_utils import write_json
from tests.migration.test_mui_select_smoke import CASES


EXPECTED_CODE_TOKENS = {
    "Progress": ("CircularProgress", "LinearProgress"),
    "Autocomplete": ("Autocomplete",),
    "Slider": ("Slider",),
}


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.json_mode_config()
    selector = MUISelectAgent(llm_config=config, use_semantic_similarity=True)
    migrator = ComponentMigrateAgent(llm_config=config)
    records = []
    try:
        for tag, source, attributes, expected in CASES:
            selection = await selector.handle_selection_request(
                MUISelectionRequest(
                    wpf_source=source,
                    wpf_tag=tag,
                    attributes=attributes,
                    max_components=3,
                ),
                None,
            )
            docs = "\n\n".join(
                f"### {name}\n{document}"
                for name, document in zip(
                    selection.selected_components, selection.docs
                )
            )
            migration = await migrator.handle_migration_request(
                ComponentMigrationRequest(
                    wpf_source=source,
                    child_react_code="",
                    mui_components_docs=docs,
                ),
                None,
            )
            code = migration.react_code
            expected_tokens = EXPECTED_CODE_TOKENS[expected]
            passed = (
                expected in selection.selected_components
                and any(token in code for token in expected_tokens)
                and "<Grid" not in code
                and "@mui/material/Progress" not in code
                and "from './" not in code
                and "from \"./" not in code
                and "```" not in code
            )
            records.append(
                {
                    "wpf_tag": tag,
                    "expected_recipe": expected,
                    "selected_components": selection.selected_components,
                    "retrieval_confidence": selection.confidence,
                    "component_name": migration.component_name,
                    "imports": migration.imports,
                    "react_code": code,
                    "passed": passed,
                }
            )
            print(
                f"{tag}: recipe={expected}, component={migration.component_name}, "
                f"passed={passed}"
            )
    finally:
        await selector.close_llm()
        await migrator.close_llm()

    write_json("outputs/component-knowledge-smoke/results.json", records)
    print(f"model={config.model}")
    print(f"passed={sum(record['passed'] for record in records)}/{len(records)}")
    print(
        "provider_calls="
        f"{selector.provider_llm_calls + migrator.provider_llm_calls}"
    )
    return all(record["passed"] for record in records)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
