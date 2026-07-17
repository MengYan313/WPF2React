"""单组件迁移 smoke：直接映射 MUI，并执行一次组件生成调用。"""

import asyncio
import sys

from dotenv import load_dotenv

from tests.migration.test_agents import test_simple_component


async def main() -> bool:
    load_dotenv(".env")
    return bool(await test_simple_component())


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
