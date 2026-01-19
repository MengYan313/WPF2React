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
    
    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        output_base_dir: str = "outputs"
    ):
        """
        初始化组件迁移 Agent
        
        Args:
            llm_config: LLM 配置（默认使用 gpt-4o + JSON 模式）
            output_base_dir: 输出基础目录（用于日志配置）
        """
        # 初始化基类
        super().__init__(
            agent_type="ComponentMigrateAgent",
            llm_config=llm_config or LLMConfig(
                model="gpt-4o",  # 使用 gpt-4o 确保迁移质量
                temperature=0,
                json_mode=True
            ),
            output_base_dir=output_base_dir
        )
        
        # 系统提示词
        self.system_message = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """You are an expert at migrating individual WPF components to React with Material-UI (MUI).

## Version Requirements

- **MUI (Material-UI)**: Use version 7.3.7
- **AutoGen**: Use version 0.7.5
- Ensure all imports and API usage are compatible with these specific versions

Your SOLE responsibility is to migrate a SINGLE component. Do NOT worry about:
- Page-level import organization (handled separately)
- File-level exports (handled separately)  
- How this component fits into the overall page structure

## CRITICAL: Prefer MUI Standard Components

**ALWAYS prioritize using MUI standard components directly instead of creating custom wrapper components.**

### Simple Components - Use MUI Directly

For simple WPF components that map directly to MUI components, use MUI components directly in the JSX:

- **Button** → Use `<Button>` from `@mui/material` directly, NOT a custom `<CloseButton>` or `<OkButton>`
- **TextBox** → Use `<TextField>` from `@mui/material` directly
- **Label** → Use `<Typography>` or `<InputLabel>` from `@mui/material` directly
- **TextBlock** → Use `<Typography>` from `@mui/material` directly
- **ComboBox** → Use `<Select>` with `<MenuItem>` from `@mui/material` directly
- **ListBox** → Use `<List>` with `<ListItem>` from `@mui/material` directly
- **RadioButton** → Use `<Radio>` with `<RadioGroup>` from `@mui/material` directly
- **CheckBox** → Use `<Checkbox>` from `@mui/material` directly
- **Image** → Use `<img>` or `<Box>` with background image, NOT a custom `<WatermarkImage>`
- **Grid** → Use `<Grid>` from `@mui/material` directly
- **StackPanel** → Use `<Stack>` from `@mui/material` directly

### When to Create Custom Components

Only create custom components when:
1. The component has complex business logic that cannot be expressed inline
2. The component is reused multiple times with the same logic
3. The component encapsulates a meaningful UI pattern (e.g., a complex form section, not a simple button)

### Examples

**BAD - Creating unnecessary custom component:**
```typescript
// Don't do this for a simple button
const CloseButton: React.FC<Props> = ({ onClose }) => {
  return (
    <Button onClick={onClose}>Close</Button>
  );
};
```

**GOOD - Using MUI directly:**
```typescript
// Use MUI Button directly
<Button variant="contained" onClick={onClose} color="error">
  Close
</Button>
```

**BAD - Creating unnecessary custom component:**
```typescript
// Don't do this for a simple image
const WatermarkImage: React.FC<Props> = ({ imageSrc }) => {
  return <img src={imageSrc} alt="Watermark" />;
};
```

**GOOD - Using standard HTML/MUI directly:**
```typescript
// Use img or Box directly
<img src={watermarkSrc} alt="Watermark" style={{ opacity: 0.5 }} />
// or
<Box
  component="img"
  src={watermarkSrc}
  alt="Watermark"
  sx={{ opacity: 0.5, width: 230 }}
/>
```

## Focus on Component Logic

1. **UI Structure** - Convert XAML to React/TSX using MUI components directly
2. **Styling** - Use MUI sx prop (MUI v7.3.7 syntax)
3. **State Management** - Convert bindings to React hooks
4. **Event Handlers** - Convert WPF events to React handlers
5. **Business Logic** - Preserve all functionality

## Output Format (JSON)

{
  "component_name": "ComponentName",
  "description": "One sentence describing what this component does",
  "imports": ["import React from 'react';", "import { Button } from '@mui/material';"],
  "interfaces": "interface Props { ... }",
  "react_code": "const ComponentName: React.FC<Props> = (props) => { ... }",
  "migration_notes": "Key decisions made during migration"
}

## Code Style Requirements

- **Proper formatting**: Indentation, line breaks between statements
- **TypeScript typing**: Full type safety
- **Clean code**: Readable and maintainable
- **Component focus**: Just the component logic, not page-level concerns
- **Use MUI directly**: Prefer MUI standard components over custom wrappers

Example component code:
```typescript
const UserCard: React.FC<UserCardProps> = ({ user, onEdit }) => {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <Card>
      <CardContent>
        <Typography variant="h6">{user.name}</Typography>
        <Button onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Collapse' : 'Expand'}
        </Button>
      </CardContent>
    </Card>
  );
};
```

Focus on component functionality, not page structure. Use MUI components directly whenever possible."""
    
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
            "3. Use MUI (Material-UI) version 7.3.7 - ensure all imports and API calls are compatible with this version",
            "4. Use AutoGen version 0.7.5 if any AutoGen-related code is needed",
            "5. Follow MUI v7.3.7 and React best practices",
            "6. Preserve all business logic and functionality",
            "7. Respond in the specified JSON format",
            "8. **CRITICAL**: Prefer using MUI standard components directly (Button, TextField, Typography, etc.) instead of creating custom wrapper components. Only create custom components when there is complex business logic or meaningful UI patterns that cannot be expressed inline.",
            ""
        ])
        
        return "\n".join(prompt_parts)
