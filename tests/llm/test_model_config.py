# -*- coding: utf-8 -*-
"""模型档位配置的离线测试。"""

import sys

from dotenv import load_dotenv

from src.llm import LLMConfig


EXPECTED_MODELS = {
    "low": "gpt-5.6-luna",
    "medium": "gpt-5.6-terra",
    "high": "gpt-5.6-sol",
}


def main() -> bool:
    load_dotenv(".env")
    resolved = {
        tier: LLMConfig.model_for_tier(tier)
        for tier in EXPECTED_MODELS
    }
    default_config = LLMConfig.marker_mode()

    success = resolved == EXPECTED_MODELS
    success = success and default_config.model == EXPECTED_MODELS["low"]
    success = success and default_config.temperature == 0
    success = success and not default_config.json_mode

    print(f"model_tiers_ok={resolved == EXPECTED_MODELS}")
    print(f"runtime_uses_low={default_config.model == EXPECTED_MODELS['low']}")
    print(f"marker_mode_ok={default_config.temperature == 0 and not default_config.json_mode}")
    return success


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
