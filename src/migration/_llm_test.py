"""
LLM 工具包使用示例（纯异步版本）

展示如何使用 src.llm 包进行各种 LLM 操作。
所有调用均为异步，需要在 async 函数中使用。
配置通过环境变量 OPENAI_API_KEY 和 OPENAI_BASE_URL 读取。
"""

import asyncio
from ..llm import (
    LLMConfig,
    AgentConfig,
    LLMClient,
    SimpleAgent,
    MessageBuilder,
    ConversationHistory,
    AgentTeam,
    parse_json_response,
    Timer,
)


async def example_1_basic_chat():
    """示例 1: 基本对话"""
    print("=" * 60)
    print("示例 1: 基本对话")
    print("=" * 60)
    
    # 创建配置（从环境变量自动读取 API key）
    config = LLMConfig(model="gpt-4o-mini")
    client = LLMClient(config)
    
    # 简单对话（异步）
    response = await client.chat(
        prompt="用一句话介绍 Python 的主要优点",
        system_message="你是一个简洁的技术顾问。"
    )
    
    print(f"\n问题: 用一句话介绍 Python 的主要优点")
    print(f"回答: {response}")
    print()


async def example_2_conversation_history():
    """示例 2: 对话历史管理"""
    print("=" * 60)
    print("示例 2: 对话历史管理")
    print("=" * 60)
    
    config = LLMConfig(model="gpt-4o-mini")
    client = LLMClient(config)
    
    # 创建对话历史
    history = ConversationHistory(
        max_messages=10,
        system_message="你是一个友好的编程助手。"
    )
    
    # 多轮对话
    conversations = [
        "我正在学习 React",
        "React 和 WPF 有什么区别？",
        "如何从 WPF 迁移到 React UI？"
    ]
    
    for user_msg in conversations:
        print(f"\n用户: {user_msg}")
        
        history.add_user_message(user_msg)
        response = await client.chat_with_history(history.get_messages())
        history.add_assistant_message(response)
        
        print(f"助手: {response}")
    
    print()


async def example_3_message_builder():
    """示例 3: 消息构建器"""
    print("=" * 60)
    print("示例 3: 消息构建器")
    print("=" * 60)
    
    # 构建复杂的多轮对话
    builder = MessageBuilder()
    builder.add_system_message("你是一个代码审查专家，专注于代码质量。")
    builder.add_user_message(
        "请审查这段代码:\n"
        "```python\n"
        "def calculate(x, y):\n"
        "    return x + y\n"
        "```"
    )
    builder.add_assistant_message("代码功能正确，但可以添加类型提示和文档字符串。")
    builder.add_user_message("请帮我改进")
    
    messages = builder.build()
    
    print(f"\n构建了 {len(messages)} 条消息:")
    for i, msg in enumerate(messages, 1):
        print(f"{i}. {msg['role']}: {msg['content'][:50]}...")
    
    config = LLMConfig(model="gpt-4o-mini")
    client = LLMClient(config)
    response = await client.chat_with_history(messages)
    
    print(f"\n最终响应:\n{response}")
    print()


async def example_4_simple_agent():
    """示例 4: 简单 Agent"""
    print("=" * 60)
    print("示例 4: 简单 Agent")
    print("=" * 60)
    
    # 创建专门的代码转换 Agent
    agent = SimpleAgent(AgentConfig(
        name="WPFToReactConverter",
        system_message=(
            "你是一个 WPF 到 React 的转换专家。\n"
            "你的任务是将 WPF XAML 代码转换为对应的 React JSX 代码。\n"
            "始终提供简洁、可运行的代码。"
        ),
        llm_config=LLMConfig(model="gpt-4o-mini", temperature=0.3)
    ))
    
    # 使用 Agent（异步）
    wpf_code = '<Button Content="Click Me" Width="100" Height="30"/>'
    response = await agent.chat(f"将这段 WPF 代码转换为 React:\n{wpf_code}")
    
    print(f"\nWPF 代码:")
    print(wpf_code)
    print(f"\nReact 代码:")
    print(response)
    print()


async def example_5_agent_team():
    """示例 5: Agent 团队协作"""
    print("=" * 60)
    print("示例 5: Agent 团队协作")
    print("=" * 60)
    
    # 创建分析 Agent
    analyzer = SimpleAgent(AgentConfig(
        name="Analyzer",
        system_message="你负责分析 WPF 代码的结构和组件。只输出分析结果，不超过 100 字。",
        llm_config=LLMConfig(model="gpt-4o-mini")
    ))
    
    # 创建转换 Agent
    converter = SimpleAgent(AgentConfig(
        name="Converter",
        system_message="你负责将 WPF 组件转换为 React 组件。只输出代码，不要解释。",
        llm_config=LLMConfig(model="gpt-4o-mini")
    ))
    
    # 创建团队
    team = AgentTeam("ConversionTeam")
    team.add_agent(analyzer)
    team.add_agent(converter)
    team.set_workflow(["Analyzer", "Converter"])
    
    # 执行工作流（异步）
    wpf_code = '<TextBox Text="{Binding Name}" Width="200"/>'
    print(f"\n输入 WPF 代码:\n{wpf_code}\n")
    
    results = await team.execute(f"处理这段 WPF 代码:\n{wpf_code}")
    
    for agent_name, response in results.items():
        print(f"\n{agent_name} 的输出:")
        print(response)
    
    print()


async def example_6_custom_config():
    """示例 6: 自定义配置"""
    print("=" * 60)
    print("示例 6: 自定义配置")
    print("=" * 60)
    
    # 创建自定义配置
    config = LLMConfig(
        model="gpt-4o",
        temperature=0.5,
        max_tokens=1000
    )
    
    client = LLMClient(config)
    response = await client.chat("说一个编程笑话")
    
    print(f"\n回答: {response}")
    print()


async def example_7_json_parsing():
    """示例 7: JSON 解析"""
    print("=" * 60)
    print("示例 7: JSON 解析")
    print("=" * 60)
    
    config = LLMConfig(model="gpt-4o-mini")
    client = LLMClient(config)
    
    # 要求 LLM 返回 JSON（异步）
    response = await client.chat(
        prompt=(
            "请返回一个 JSON 对象，包含以下信息:\n"
            "- name: React\n"
            "- type: library\n"
            "- language: JavaScript\n"
            "请用 JSON 格式返回"
        ),
        system_message="你总是返回有效的 JSON 格式。"
    )
    
    print(f"\nLLM 原始响应:\n{response}\n")
    
    # 解析 JSON
    data = parse_json_response(response)
    if data:
        print(f"解析后的 JSON:")
        print(f"  name: {data.get('name')}")
        print(f"  type: {data.get('type')}")
        print(f"  language: {data.get('language')}")
    else:
        print("JSON 解析失败")
    
    print()


async def example_8_json_mode():
    """示例 8: JSON 模式（强制返回 JSON）"""
    print("=" * 60)
    print("示例 8: JSON 模式（强制返回 JSON）")
    print("=" * 60)
    
    # 创建启用 JSON 模式的配置
    config = LLMConfig(model="gpt-4o-mini", json_mode=True)
    client = LLMClient(config)
    
    # 使用 JSON 模式请求
    response = await client.chat(
        prompt="分析 WPF 的 Button 控件，返回其基本属性信息",
        system_message=(
            "你是一个 WPF 专家。返回 JSON 格式，包含以下字段：\n"
            "- name: 控件名称\n"
            "- category: 控件类别\n"
            "- common_properties: 常用属性列表（数组）\n"
            "- description: 简短描述"
        )
    )
    
    print(f"\nJSON 模式响应:\n{response}\n")
    
    # 解析 JSON
    data = parse_json_response(response)
    if data:
        print(f"解析成功:")
        print(f"  名称: {data.get('name')}")
        print(f"  类别: {data.get('category')}")
        print(f"  常用属性: {', '.join(data.get('common_properties', []))}")
        print(f"  描述: {data.get('description')}")
    
    print()


async def example_9_batch_parallel():
    """示例 9: 批量并发处理"""
    print("=" * 60)
    print("示例 9: 批量并发处理")
    print("=" * 60)
    
    config = LLMConfig(model="gpt-4o-mini")
    client = LLMClient(config)
    
    # 批量并发请求
    prompts = [
        "用一句话介绍 Python",
        "用一句话介绍 JavaScript",
        "用一句话介绍 TypeScript"
    ]
    
    print(f"\n批量处理 {len(prompts)} 个问题（并发）...\n")
    
    responses = await client.batch_chat(
        prompts=prompts,
        system_message="你是一个简洁的技术顾问，用一句话回答。"
    )
    
    for prompt, response in zip(prompts, responses):
        print(f"问题: {prompt}")
        print(f"回答: {response}\n")


async def main():
    """运行所有示例"""
    # 尝试加载 .env 文件
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✓ 已加载 .env 文件")
    except ImportError:
        print("提示: 安装 python-dotenv 可自动加载 .env 文件")
    
    print("\n" + "=" * 60)
    print(" " * 10 + "LLM 工具包使用示例（纯异步版本）")
    print("=" * 60 + "\n")
    
    examples = [
        # ("基本对话", example_1_basic_chat),
        # ("对话历史管理", example_2_conversation_history),
        # ("消息构建器", example_3_message_builder),
        # ("简单 Agent", example_4_simple_agent),
        # ("Agent 团队协作", example_5_agent_team),
        # ("自定义配置", example_6_custom_config),
        # ("JSON 解析", example_7_json_parsing),
        # ("JSON 模式（强制返回 JSON）", example_8_json_mode),
        # ("批量并发处理", example_9_batch_parallel),
    ]
    
    for i, (name, func) in enumerate(examples, 1):
        try:
            print(f"\n运行示例 {i}/{len(examples)}: {name}")
            await func()
        except Exception as e:
            print(f"\n示例 {i} 运行失败: {e}")
            print("请确保已设置 OPENAI_API_KEY 环境变量")
            if i == 1:  # 如果第一个示例就失败了，直接退出
                print("\n跳过剩余示例...")
                break
            continue
    
    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60 + "\n")


# python -m src.migration._llm_test
if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
