"""基于共享 Agent 基础设施构建的迁移专用兼容基类。"""

from pathlib import Path
from typing import Any, Mapping, Optional

from src.agents.base import BaseRoutedAgent
from src.llm import LLMConfig
from src.llm.json_output import JsonOutputError, complete_json_object

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
        self.logical_llm_calls = 0
        self.provider_llm_calls = 0

    async def call_json(
        self,
        system_message: str,
        user_message: str,
        schema: Mapping[str, Any],
    ) -> dict[str, Any]:
        """调用共享 JSON 流程，并记录逻辑调用与包含修复的 provider 调用。"""
        if self.llm_client is None:
            raise ValueError("迁移 Agent 未配置 LLM 客户端")
        self.logical_llm_calls += 1
        agent = self
        delegate = self.llm_client.model_client

        class CountingModelClient:
            async def create(self, *args: Any, **kwargs: Any) -> Any:
                agent.provider_llm_calls += 1
                return await delegate.create(*args, **kwargs)

        return await complete_json_object(
            CountingModelClient(),
            system_message,
            user_message,
            schema,
            logger=self.logger,
            max_tokens=self.llm_client.config.max_tokens,
        )

    def llm_usage_snapshot(self) -> dict[str, int]:
        """返回当前 Runtime Agent 的 provider 实际 token 与调用计数。"""
        prompt_tokens = 0
        completion_tokens = 0
        if self.llm_client is not None:
            usage_method = getattr(self.llm_client.model_client, "actual_usage", None)
            if callable(usage_method):
                usage = usage_method()
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(
                    getattr(usage, "completion_tokens", 0) or 0
                )
        return {
            "logical_calls": self.logical_llm_calls,
            "provider_calls": self.provider_llm_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

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
