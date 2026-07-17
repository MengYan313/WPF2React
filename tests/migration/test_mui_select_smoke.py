# -*- coding: utf-8 -*-
"""使用合成自定义控件验证 MUI 描述生成和语义选择链路。"""

import asyncio
import sys

from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration.messages import MUISelectionRequest
from src.migration.mui_select_agent import MUISelectAgent


SYNTHETIC_CONTROL = """\
<PulseIndicator IsActive="True" Label="Synthetic status" />
"""


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.marker_mode()
    agent = MUISelectAgent(llm_config=config, use_semantic_similarity=True)

    try:
        response = await agent.handle_selection_request(
            MUISelectionRequest(
                wpf_source=SYNTHETIC_CONTROL,
                wpf_tag="PulseIndicator",
                max_components=3,
            ),
            None,  # handler does not use MessageContext
        )
    finally:
        if agent.llm_client:
            await agent.llm_client.close()

    success = bool(response.selected_components)
    success = success and len(response.selected_components) == len(response.docs)
    print(f"model={config.model}")
    print(f"selection_nonempty={bool(response.selected_components)}")
    print(f"docs_aligned={len(response.selected_components) == len(response.docs)}")
    return success


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
