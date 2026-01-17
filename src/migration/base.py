# -*- coding: utf-8 -*-
"""
Base Agent using Autogen Official API

基于 Autogen 官方 RoutedAgent 的基类实现。
"""

from typing import Optional, Callable
from autogen_core import RoutedAgent, MessageContext, default_subscription
from src.logger import get_logger


@default_subscription
class BaseMigrationAgent(RoutedAgent):
    """
    迁移 Agent 基类
    
    继承自 Autogen 官方的 RoutedAgent，提供 LLM 客户端支持。
    子类需要使用 @message_handler 装饰器定义消息处理方法。
    
    使用 @default_subscription 装饰器，使 Agent 可以接收默认主题的消息。
    """
    
    def __init__(
        self, 
        agent_type: str,
        llm_config: Optional['LLMConfig'] = None,  # type: ignore
        output_base_dir: str = "outputs"
    ):
        """
        初始化 Agent
        
        Args:
            agent_type: Agent 类型名称（用于标识）
            llm_config: LLM 配置（可选）
            output_base_dir: 输出基础目录（用于日志配置）
        """
        super().__init__(agent_type)
        
        # 创建日志记录器（自动检测脚本名称）
        self.logger = get_logger(name=agent_type)
        
        # 创建 LLM 客户端
        if llm_config:
            from src.llm import LLMClient
            self.llm_client = LLMClient(llm_config)
        else:
            self.llm_client = None
    
    async def call_llm(
        self,
        system_message: str,
        user_message: str,
        **kwargs
    ) -> str:
        """
        调用 LLM 的便捷方法
        
        Args:
            system_message: 系统消息
            user_message: 用户消息
            **kwargs: 其他参数传递给 LLM
        
        Returns:
            LLM 响应文本
        """
        if not self.llm_client:
            raise ValueError(f"Agent {self.id.type} 未配置 LLM 客户端")
        
        return await self.llm_client.create(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            **kwargs
        )
