"""基于共享 Agent 基础设施构建的迁移专用兼容基类。"""

from pathlib import Path
from typing import Optional

from src.agents.base import BaseRoutedAgent
from src.llm import LLMConfig
from src.llm.json_output import JsonOutputError

from .json_schemas import TYPESCRIPT_CODE_SCHEMA


class BaseMigrationAgent(BaseRoutedAgent):
    """WPF 迁移 Agent 的基类。"""

    def __init__(
        self,
        agent_type: str,
        llm_config: Optional[LLMConfig] = None,
        output_base_dir: str = "outputs",
    ) -> None:
        super().__init__(agent_type, llm_config)
        self.output_base_dir = Path(output_base_dir)

    async def request_typescript_code(
        self,
        system_message: str,
        user_message: str,
    ) -> str:
        """请求完整 TypeScript/TSX 源码；JSON 单次修复失败时返回空串。"""
        try:
            data = await self.call_json(
                system_message,
                user_message,
                TYPESCRIPT_CODE_SCHEMA,
            )
        except JsonOutputError as exc:
            self.logger.error("TypeScript JSON 响应无效: %s", exc)
            return ""
        return str(data["typescript_code"]).strip()
