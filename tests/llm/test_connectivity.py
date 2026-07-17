# -*- coding: utf-8 -*-
"""单次低档模型连通性 smoke，不输出密钥、中转站地址或完整响应。"""

import asyncio
import sys

from dotenv import load_dotenv

from src.llm import LLMClient, LLMConfig


async def main() -> bool:
    load_dotenv(".env")
    config = LLMConfig.marker_mode()
    client = LLMClient(config)

    try:
        response = await asyncio.wait_for(
            client.chat(
                prompt="Reply with exactly: WPF2REACT_SMOKE_OK",
                system_message="Follow the user's formatting instruction exactly.",
                max_tokens=32,
            ),
            timeout=60,
        )
    except Exception as exc:
        print(f"model={config.model}")
        print(f"request_failed={type(exc).__name__}")
        return False
    finally:
        await client.close()

    normalized = response.strip()
    success = "WPF2REACT_SMOKE_OK" in normalized
    print(f"model={config.model}")
    print(f"response_nonempty={bool(normalized)}")
    print(f"marker_ok={success}")
    return success


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
