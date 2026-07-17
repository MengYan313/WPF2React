"""
LLM 工具包使用示例

展示如何使用 src.llm 包进行各种 LLM 操作。
所有调用均为异步，需要在 async 函数中使用。

运行方式：
    .venv/bin/python -m tests.llm.test_examples
"""

import asyncio
import sys

from src.llm import (
    LLMConfig,
    AgentConfig,
    LLMClient,
    SimpleAgent,
    MessageBuilder,
    ConversationHistory,
    AgentTeam,
    complete_json_object,
)


async def example_basic_chat():
    """示例: 基本对话"""
    print("=" * 60)
    print("示例: 基本对话")
    print("=" * 60)
    
    # 创建配置（从环境变量自动读取 API key）
    config = LLMConfig()
    client = LLMClient(config)
    
    # 简单对话（异步）
    response = await client.chat(
        prompt="用一句话介绍 Python 的主要优点",
        system_message="你是一个简洁的技术顾问。"
    )
    
    print(f"\n问题: 用一句话介绍 Python 的主要优点")
    print(f"回答: {response}")
    print()


async def example_simple_agent():
    """示例: 简单 Agent"""
    print("=" * 60)
    print("示例: 简单 Agent")
    print("=" * 60)
    
    # 创建专门的代码转换 Agent
    agent = SimpleAgent(AgentConfig(
        name="WPFToReactConverter",
        system_message=(
            "你是一个 WPF 到 React 的转换专家。\n"
            "你的任务是将 WPF XAML 代码转换为对应的 React TSX 代码。\n"
            "始终提供简洁、可运行的代码。"
        ),
        llm_config=LLMConfig(
            model=LLMConfig.model_for_tier("low"),
            temperature=0.3,
        )
    ))
    
    # 使用 Agent（异步）
    wpf_code = '<Button Content="Click Me" Width="100" Height="30"/>'
    response = await agent.chat(f"将这段 WPF 代码转换为 React:\n{wpf_code}")
    
    print(f"\nWPF 代码:")
    print(wpf_code)
    print(f"\nReact 代码:")
    print(response)
    print()


async def example_json_mode():
    """示例: JSON 模式（强制返回 JSON）"""
    print("=" * 60)
    print("示例: JSON 模式（强制返回 JSON）")
    print("=" * 60)
    
    # 创建启用 JSON 模式的配置
    config = LLMConfig.json_mode_config()
    client = LLMClient(config)
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "category": {"type": "string"},
            "common_properties": {
                "type": "array",
                "items": {"type": "string"},
            },
            "description": {"type": "string"},
        },
        "required": ["name", "category", "common_properties", "description"],
        "additionalProperties": False,
    }
    try:
        data = await complete_json_object(
            client.model_client,
            "你是 WPF 控件分析专家，所有说明使用中文。",
            "分析 WPF Button 控件的名称、类别、常用属性和用途。",
            schema,
        )
    finally:
        await client.close()

    print("\nJSON 模式解析成功：")
    print(f"  名称: {data.get('name')}")
    print(f"  类别: {data.get('category')}")
    print(f"  常用属性: {', '.join(data.get('common_properties', []))}")
    print(f"  描述: {data.get('description')}")
    
    print()


async def example_agent_team():
    """示例: Agent 团队协作"""
    print("=" * 60)
    print("示例: Agent 团队协作")
    print("=" * 60)
    
    # 创建分析 Agent
    analyzer = SimpleAgent(AgentConfig(
        name="Analyzer",
        system_message="你负责分析 WPF 代码的结构和组件。只输出分析结果，不超过 100 字。",
        llm_config=LLMConfig()
    ))
    
    # 创建转换 Agent
    converter = SimpleAgent(AgentConfig(
        name="Converter",
        system_message="你负责将 WPF 组件转换为 React 组件。只输出代码，不要解释。",
        llm_config=LLMConfig()
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


async def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print(" " * 10 + "LLM 工具包使用示例")
    print("=" * 60 + "\n")
    
    examples = [
        ("基本对话", example_basic_chat),
        ("简单 Agent", example_simple_agent),
        ("JSON 模式", example_json_mode),
        ("Agent 团队协作", example_agent_team),
    ]
    
    failed = []
    for i, (name, func) in enumerate(examples, 1):
        try:
            print(f"\n[{i}/{len(examples)}] 运行示例: {name}")
            await func()
        except Exception as e:
            failed.append(name)
            print(f"\n示例失败: {e}")
            import traceback
            traceback.print_exc()
            if i == 1:  # 如果第一个示例就失败了，提示并继续
                print("\n请确保已设置 OPENAI_API_KEY 环境变量")
            continue
    
    print("\n" + "=" * 60)
    print("所有示例运行完成")
    print("=" * 60)
    if failed:
        print(f"失败示例: {', '.join(failed)}")
        return False
    return True


# 运行示例：.venv/bin/python -m tests.llm.test_examples
if __name__ == "__main__":
    # 加载环境变量
    try:
        from dotenv import load_dotenv
        load_dotenv('.env')
        print("✓ 已加载 .env 文件")
    except ImportError:
        print("⚠ python-dotenv 未安装")
    except Exception as e:
        print(f"⚠ 加载 .env 文件失败: {e}")
    
    # 运行异步主函数
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
