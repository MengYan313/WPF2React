# -*- coding: utf-8 -*-
"""
Component Migration Agent

负责将单个 WPF 组件迁移为 React 组件。
"""

import json
from typing import Optional

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import ComponentMigrationRequest, ComponentMigrationResponse


class ComponentMigrateAgent(BaseMigrationAgent):
    """
    组件迁移 Agent
    
    职责：
    1. 接收 WPF 组件源代码
    2. 接收依赖代码和子组件 React 代码
    3. 接收 MUI 组件文档
    4. 使用 LLM 完成迁移
    5. 返回结构化的迁移结果
    """
    
    def __init__(self, llm_config: Optional[LLMConfig] = None):
        """
        初始化组件迁移 Agent
        
        Args:
            llm_config: LLM 配置（默认使用 gpt-4o + JSON 模式）
        """
        # 初始化基类
        super().__init__(
            agent_type="ComponentMigrateAgent",
            llm_config=llm_config or LLMConfig(
                model="gpt-4o",  # 使用 gpt-4o 确保迁移质量
                temperature=0,
                json_mode=True
            )
        )
        
        # 系统提示词
        self.system_message = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """You are an expert software engineer specializing in migrating WPF applications to React with Material-UI (MUI).

Your task is to migrate a single WPF component to a React component using MUI.

## Migration Guidelines

1. **UI Structure**: Convert XAML layout to React/TSX structure
2. **Styling**: Use MUI's sx prop or styled components for styling
3. **Data Binding**: Convert WPF bindings to React state/props
4. **Event Handlers**: Convert WPF events to React event handlers
5. **Business Logic**: Preserve all business logic and functionality

## Output Format

You must respond in JSON format with the following structure:
{
  "component_name": "ComponentName",
  "description": "Brief description of the component",
  "imports": ["import statements as array of strings"],
  "interfaces": "TypeScript interface definitions if needed",
  "react_code": "The complete React component code",
  "migration_notes": "Any important notes about the migration"
}

## Code Formatting Requirements (IMPORTANT)

**The "react_code" field must contain properly formatted TypeScript/React code with:**
- Proper indentation (2 spaces per level)
- Line breaks between statements
- Line breaks between JSX elements
- Readable, well-structured code (NOT compressed into a single line)

Example of GOOD formatting:
```typescript
const MyComponent: React.FC<MyComponentProps> = ({ prop1, prop2 }) => {
  const [state, setState] = useState('');
  
  return (
    <Box sx={{ padding: 2 }}>
      <Typography variant="h6">
        {prop1}
      </Typography>
      <Button onClick={() => setState('clicked')}>
        Click Me
      </Button>
    </Box>
  );
};

export default MyComponent;
```

Example of BAD formatting (DO NOT do this):
```typescript
const MyComponent: React.FC<MyComponentProps> = ({ prop1, prop2 }) => { const [state, setState] = useState(''); return ( <Box sx={{ padding: 2 }}><Typography variant="h6">{prop1}</Typography><Button onClick={() => setState('clicked')}>Click Me</Button></Box> ); }; export default MyComponent;
```

## Quality Requirements

- Generate clean, maintainable TypeScript/TSX code with proper formatting
- Follow React and MUI best practices
- Use proper TypeScript typing
- Include helpful comments for complex logic
- Ensure the component is functional and production-ready
- **ALWAYS format the code with proper line breaks and indentation**
"""
    
    @message_handler
    async def handle_migration_request(
        self, 
        message: ComponentMigrationRequest, 
        ctx: MessageContext
    ) -> ComponentMigrationResponse:
        """
        处理组件迁移请求
        
        Args:
            message: 组件迁移请求消息
            ctx: 消息上下文
        
        Returns:
            组件迁移响应消息
        """
        # 1. 构建用户提示词
        user_prompt = self._build_user_prompt(
            wpf_source=message.wpf_source,
            dependencies_code=message.dependencies_code,
            child_react_code=message.child_react_code,
            mui_components_docs=message.mui_components_docs
        )
        
        # 2. 调用 LLM 完成迁移
        response = await self.call_llm(
            system_message=self.system_message,
            user_message=user_prompt
        )
        
        # 3. 验证 JSON 格式并解析
        try:
            # 清理可能的 markdown 代码块标记
            cleaned_response = response.strip()
            if cleaned_response.startswith("```"):
                # 移除开头的 ```json 或 ```
                lines = cleaned_response.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # 移除结尾的 ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned_response = '\n'.join(lines)
            
            result = json.loads(cleaned_response)
            
            # 确保必需字段存在
            required_fields = ["component_name", "react_code"]
            for field in required_fields:
                if field not in result:
                    result[field] = f"Error: Missing {field}"
            
            # 提取所有字段（使用默认值）
            component_name = result.get("component_name", "UnknownComponent")
            description = result.get("description", "")
            imports = result.get("imports", [])
            interfaces = result.get("interfaces", "")
            react_code = result.get("react_code", "")
            migration_notes = result.get("migration_notes", "")
            
            return ComponentMigrationResponse(
                component_name=component_name,
                description=description,
                imports=imports if isinstance(imports, list) else [],
                interfaces=interfaces,
                react_code=react_code,
                migration_notes=migration_notes
            )
            
        except json.JSONDecodeError as e:
            # JSON 解析失败，返回错误信息
            return ComponentMigrationResponse(
                component_name="MigrationError",
                description="JSON 解析失败",
                imports=[],
                interfaces="",
                react_code=f"// JSON 解析错误: {e}\n// 原始响应:\n{response}",
                migration_notes=f"迁移失败: JSON 解析错误 - {e}"
            )
    
    def _build_user_prompt(
        self,
        wpf_source: str,
        dependencies_code: str,
        child_react_code: str,
        mui_components_docs: str
    ) -> str:
        """构建用户提示词"""
        prompt_parts = [
            "# Task",
            "",
            "Migrate the following WPF component to a React component using Material-UI.",
            "",
            "## WPF Source Code",
            "",
            "```xaml",
            wpf_source,
            "```",
            ""
        ]
        
        # 添加依赖代码（如果有）
        if dependencies_code and dependencies_code.strip():
            prompt_parts.extend([
                "## Dependencies Code (e.g., ViewModel, Business Logic)",
                "",
                "```csharp",
                dependencies_code,
                "```",
                ""
            ])
        
        # 添加子组件代码（如果有）
        if child_react_code and child_react_code.strip():
            prompt_parts.extend([
                "## Child Components (Already Migrated)",
                "",
                "The following child components have been migrated to React. You can reference them in your implementation.",
                "",
                "```typescript",
                child_react_code,
                "```",
                ""
            ])
        
        # 添加 MUI 文档（如果有）
        if mui_components_docs and mui_components_docs.strip():
            prompt_parts.extend([
                "## Relevant MUI Component Documentation",
                "",
                mui_components_docs,
                ""
            ])
        
        # 添加要求
        prompt_parts.extend([
            "## Requirements",
            "",
            "1. Create a production-ready React component",
            "2. Use TypeScript for type safety",
            "3. Follow MUI and React best practices",
            "4. Preserve all business logic and functionality",
            "5. Respond in the specified JSON format",
            ""
        ])
        
        return "\n".join(prompt_parts)
