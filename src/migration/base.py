"""Migration-specific compatibility base built on shared Agent infrastructure."""

from pathlib import Path
from typing import Optional

from src.agents.base import BaseRoutedAgent
from src.llm import LLMConfig


class BaseMigrationAgent(BaseRoutedAgent):
    """Base class for WPF migration Agents."""

    def __init__(
        self,
        agent_type: str,
        llm_config: Optional[LLMConfig] = None,
        output_base_dir: str = "outputs",
    ) -> None:
        super().__init__(agent_type, llm_config)
        self.output_base_dir = Path(output_base_dir)
