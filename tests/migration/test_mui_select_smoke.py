"""使用少量真实 LLM 调用验证未登记自建控件的混合召回。"""

import asyncio
import sys

from dotenv import load_dotenv

from src.llm import LLMConfig
from src.migration.messages import MUISelectionRequest
from src.migration.mui_select_agent import MUISelectAgent


CASES = (
    (
        "BusySpinner",
        '<local:BusySpinner IsRunning="True" Label="Loading results" />',
        {"IsRunning": "True", "Label": "Loading results"},
        "Progress",
    ),
    (
        "SearchSuggestInput",
        '<local:SearchSuggestInput Query="{Binding Query}" ItemsSource="{Binding Suggestions}" />',
        {"Query": "{Binding Query}", "ItemsSource": "{Binding Suggestions}"},
        "Autocomplete",
    ),
    (
        "SoundLevelControl",
        '<local:SoundLevelControl Value="{Binding Volume}" Minimum="0" Maximum="100" />',
        {"Value": "{Binding Volume}", "Minimum": "0", "Maximum": "100"},
        "Slider",
    ),
)


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.json_mode_config()
    agent = MUISelectAgent(llm_config=config, use_semantic_similarity=True)
    reciprocal_ranks = []
    try:
        for tag, source, attributes, expected in CASES:
            response = await agent.handle_selection_request(
                MUISelectionRequest(
                    wpf_source=source,
                    wpf_tag=tag,
                    attributes=attributes,
                    max_components=3,
                ),
                None,
            )
            names = response.selected_components
            rank = names.index(expected) + 1 if expected in names else 0
            reciprocal_ranks.append(1 / rank if rank else 0)
            print(
                f"{tag}: expected={expected}, rank={rank}, "
                f"candidates={names}, confidence={response.confidence:.4f}"
            )
    finally:
        await agent.close_llm()

    recall_at_3 = sum(value > 0 for value in reciprocal_ranks) / len(CASES)
    mean_reciprocal_rank = sum(reciprocal_ranks) / len(CASES)
    print(f"model={config.model}")
    print(f"recall_at_3={recall_at_3:.4f}")
    print(f"mrr={mean_reciprocal_rank:.4f}")
    return recall_at_3 == 1.0 and mean_reciprocal_rank >= 0.8


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
