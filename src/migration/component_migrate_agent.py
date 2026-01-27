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
            llm_config: LLM 配置（默认使用 gpt-4o，使用标记格式）
            output_base_dir: 输出基础目录（用于日志配置）
        """
        # 初始化基类
        super().__init__(
            agent_type="ComponentMigrateAgent",
            llm_config=llm_config or LLMConfig(
                model="gpt-4o",  # 使用 gpt-4o 确保迁移质量
                temperature=0,
                json_mode=False  # 使用标记格式，不使用 JSON 模式
            ),
            output_base_dir=output_base_dir
        )
        
        # 系统提示词
        self.system_message = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """You are an expert at migrating individual WPF components to React with Material-UI (MUI).

## Version Requirements

- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- **AutoGen**: Use version 0.7.5
- Ensure all imports and API usage are compatible with these specific versions

Your SOLE responsibility is to migrate a SINGLE component. Do NOT worry about:
- Page-level import organization (handled separately)
- File-level exports (handled separately)  
- How this component fits into the overall page structure

## Migration Process (Chain of Thought)

Follow these steps in order:

### Step 1: Analyze WPF Component
Analyze and summarize the key attributes and layout characteristics of the original WPF component:
- Identify the component type and its purpose
- List key properties (attributes, bindings, events)
- Understand the layout structure (Grid, StackPanel, etc.)
- Note any styling or visual characteristics
- Identify event handlers and data bindings

### Step 2: Select MUI Components
Use the provided MUI component documentation to select appropriate components for migration:
- **CRITICAL**: If MUI components are provided with usage examples, you MUST follow those examples EXACTLY
- Use the SIMPLEST and MOST COMMON APIs from the usage examples - do NOT use advanced or complex features
- If no MUI components are provided, autonomously select the most suitable MUI components
- If no suitable MUI component exists, create a custom React component
- Consider component composition (combining multiple MUI components if needed)

### Step 3: Migrate with Simplicity Principle
Follow the simplicity principle - use the least code and simplest logic to complete the migration:
- **CRITICAL: Follow Usage Examples**: When MUI component usage examples are provided, use the EXACT same API pattern from the example
- **Use Simplest APIs**: Only use the most basic and common props/APIs shown in the examples - avoid advanced features, custom configurations, or complex patterns
- **Minimize code complexity**: Avoid unnecessary abstractions or wrappers
- **Ignore unnecessary styles**: Only preserve essential visual characteristics
- **Prefer onClick for events**: All click events and page navigation should prioritize onClick implementation
- **Use MUI directly**: Prefer standard MUI components over custom wrappers
- **Simplify state management**: Use the simplest React hooks (useState) unless complex state is required
- **Complete Component Structure**: For Dialog components, ALWAYS use Dialog, DialogTitle, DialogContent, DialogActions as shown in examples
- **No Custom Methods**: Do NOT create custom methods that don't exist in the examples (e.g., don't use `getTotal()` if not in the example)

## CRITICAL: Prefer MUI Standard Components

**ALWAYS prioritize using MUI standard components directly instead of creating custom wrapper components.**

### Simple Components - Use MUI Directly

For simple WPF components that map directly to MUI components, use MUI components directly in the TSX:

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

## Implementation Guidelines

1. **Follow Usage Examples EXACTLY** - When MUI component usage examples are provided:
   - Use the EXACT same import statements from the example
   - Use the EXACT same component structure (e.g., Dialog must include DialogTitle, DialogContent, DialogActions)
   - Use the EXACT same props pattern (e.g., `open` and `onClose` for Dialog)
   - Use the SIMPLEST API shown in the example - do NOT add advanced features
   - Do NOT use methods or APIs that are NOT shown in the example

2. **UI Structure** - Convert XAML to React/TSX using MUI components directly:
   - For Dialog/Modal components: ALWAYS wrap content in `<Dialog open={open} onClose={onClose}>` with `<DialogTitle>`, `<DialogContent>`, and optionally `<DialogActions>`
   - For Grid layouts: Use `<Grid container>` and `<Grid item xs={...}>` as shown in examples
   - For DataGrid: Ensure each row has an `id` field, use the simplest column configuration

3. **Styling** - Use MUI sx prop (MUI v5.18.0 syntax), only preserve essential styles:
   - Use simple sx props like `sx={{ p: 2 }}` or `sx={{ width: '100%' }}`
   - Avoid complex styling - focus on layout and basic appearance

4. **State Management** - Convert bindings to React hooks, prefer useState unless complex state is needed:
   - Use `useState` for simple state (dialog open/close, form values)
   - Keep state management minimal

5. **Event Handlers** - Convert WPF events to React handlers, use onClick for all click events and navigation:
   - Use simple `onClick` handlers: `onClick={() => setOpen(true)}`
   - Use `onChange` for form inputs: `onChange={(e) => setValue(e.target.value)}`

6. **Business Logic** - Preserve all functionality, but simplify implementation where possible:
   - Use direct property access (e.g., `expenseData.alias`) instead of custom getters
   - Use simple calculations instead of complex methods
   - Do NOT create methods that don't exist in the original or examples

7. **Data Property Names** - CRITICAL: When accessing data from imported data resources:
   - **ALL property names MUST use lowercase camelCase** (e.g., `expenseData.alias`, `expenseData.employeeNumber`, `expenseData.costCenter`, `expenseData.lineItems`)
   - Do NOT use PascalCase property names (e.g., `expenseData.Alias`, `expenseData.EmployeeNumber`)
   - This applies to all data objects imported from `data.ts` or provided in the data resource information
   - Example: `const alias = expenseData.alias;` (NOT `expenseData.Alias`)

## Output Format

**Output your response wrapped in the following tags:**

[Component Name]
ComponentName
[/Component Name]

[Description]
One sentence describing what this component does
[/Description]

[Imports]
import React from 'react';
import {{ Button }} from '@mui/material';
...
[/Imports]

[Interfaces]
interface Props {{
  ...
}}
[/Interfaces]

[React Code]
const ComponentName: React.FC<Props> = (props) => {{
  ...
}}
[/React Code]

[Migration Notes]
Key decisions made during migration
[/Migration Notes]

**Important**: 
- List each import statement on a separate line in `[Imports]` section
- Do NOT use markdown code blocks (```)
- Use the tags above to structure your response

## Code Style Requirements

- **Proper formatting**: Indentation, line breaks between statements
- **TypeScript typing**: Full type safety
- **Clean code**: Readable and maintainable
- **Component focus**: Just the component logic, not page-level concerns
- **Use MUI directly**: Prefer MUI standard components over custom wrappers
- **Follow Examples**: When usage examples are provided, match the code style and structure from the examples

## CRITICAL: Common MUI Component Patterns

### Dialog Components
ALWAYS use this structure when creating dialogs:
```typescript
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';

interface DialogProps {
  open: boolean;
  onClose: () => void;
}

export function MyDialog({ open, onClose }: DialogProps) {
  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>Title</DialogTitle>
      <DialogContent>
        {/* Content here */}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
```

### Grid Layout
Use the simplest Grid pattern:
```typescript
import Grid from '@mui/material/Grid';

<Grid container spacing={2}>
  <Grid item xs={12}>
    {/* Content */}
  </Grid>
  <Grid item xs={6}>
    {/* Content */}
  </Grid>
</Grid>
```

### DataGrid
Use the simplest DataGrid configuration:
```typescript
import { DataGrid } from '@mui/x-data-grid';

<DataGrid
  rows={rows.map((row, index) => ({ ...row, id: row.id || index }))}
  columns={[
    { field: 'field1', headerName: 'Header 1' },
    { field: 'field2', headerName: 'Header 2' },
  ]}
/>
```

**IMPORTANT**: Always ensure rows have an `id` field for DataGrid to work correctly.

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
            child_react_code=message.child_react_code,
            mui_components_docs=message.mui_components_docs,
            template=message.template,
            data=message.data
        )
        
        # 2. 调用 LLM 完成迁移
        response = await self.call_llm(
            system_message=self.system_message,
            user_message=user_prompt
        )
        
        # 3. 从标记中提取各个字段
        import re
        cleaned_response = response.strip()
        
        # 使用统一的标记提取工具
        from src.migration.utils import extract_tag_content, extract_tag_content_lines
        
        # 提取各个字段
        component_name = extract_tag_content(response, "Component Name", "UnknownComponent", self.logger)
        description = extract_tag_content(response, "Description", "", self.logger)
        interfaces = extract_tag_content(response, "Interfaces", "", self.logger)
        react_code = extract_tag_content(response, "React Code", "", self.logger)
        migration_notes = extract_tag_content(response, "Migration Notes", "", self.logger)
        
        # 提取 imports（需要按行分割）
        imports_lines = extract_tag_content_lines(response, "Imports", [], self.logger)
        # 过滤空行和注释
        imports = [
            line.strip() 
            for line in imports_lines 
            if line.strip() and not line.strip().startswith('//')
        ]
        
        # 解析成功后不要验证，直接使用提取的内容
        # 如果字段为空，使用默认值（已在 extract_field 中处理）
        if not component_name or component_name == "UnknownComponent":
            component_name = "MigrationError"
        
        if not react_code:
            react_code = f"// 错误: 无法从 LLM 响应中提取 React 代码\n// 原始响应:\n{response}"
            migration_notes = f"迁移失败: 无法提取 React 代码。{migration_notes}"
        
        return ComponentMigrationResponse(
            component_name=component_name,
            description=description,
            imports=imports,
            interfaces=interfaces,
            react_code=react_code,
            migration_notes=migration_notes
        )
    
    def _build_user_prompt(
        self,
        wpf_source: str,
        child_react_code: str,
        mui_components_docs: str,
        template: str = "",
        data: dict = None
    ) -> str:
        """构建用户提示词"""
        if data is None:
            data = {}
            
        prompt_parts = [
            "# Task",
            "",
            "Migrate the following WPF component to a React component using Material-UI.",
            "",
            "[WPF Source Code]",
            wpf_source,
            "[/WPF Source Code]",
            ""
        ]
        
        # 添加模板代码（如果有）
        if template and template.strip():
            prompt_parts.extend([
                "The following template is referenced by this component. Use it to understand the data structure and rendering logic.",
                "[Template Code]",
                template,
                "[/Template Code]",
                ""
            ])
        
        # 添加数据资源信息（如果有）
        if data and len(data) > 0:
            # 检查是否是迁移后的数据格式（包含 ts_code 和 import_statement）
            if 'ts_code' in data and 'import_statement' in data:
                # 使用迁移后的数据格式
                prompt_parts.extend([
                    "The following data resource is referenced by this component. It has been migrated to TypeScript.",
                    "Use the migrated TypeScript code and import statement to understand how to use this data in your component.",
                    "",
                    "[Data Resource - Import Statement]",
                    data.get('import_statement', ''),
                    "[/Data Resource - Import Statement]",
                    "",
                    "[Data Resource - TypeScript Code]",
                    data.get('ts_code', ''),
                    "[/Data Resource - TypeScript Code]",
                    "",
                    "Important:",
                    "- Use the import statement above to import the data in your component",
                    "- The TypeScript code shows the data structure and how it's defined",
                    "- Use the imported data constant directly in your component",
                    "- **CRITICAL: Property Names**: ALL data property names MUST use lowercase camelCase (e.g., `expenseData.alias`, `expenseData.employeeNumber`, `expenseData.costCenter`, `expenseData.lineItems`)",
                    "- Do NOT use PascalCase property names (e.g., `expenseData.Alias`, `expenseData.EmployeeNumber`, `expenseData.CostCenter`)",
                    "- When accessing data properties in your component, always use lowercase property names",
                    "- Example: `const alias = expenseData.alias;` (NOT `expenseData.Alias`)",
                    ""
                ])
            else:
                # 使用原始 WPF 数据格式（向后兼容）
                data_info_parts = []
                data_info_parts.append(f"Data Resource Key: {data.get('key', 'N/A')}")
                data_info_parts.append(f"Data Resource Type: {data.get('data_resource_type', 'N/A')}")
                data_info_parts.append(f"Source File: {data.get('source_file', 'N/A')}")
                
                # 添加数据资源的源代码（如果有）
                if data.get('source_code'):
                    data_info_parts.append("")
                    data_info_parts.append("Data Resource Source Code:")
                    data_info_parts.append(data.get('source_code'))
                
                # 添加数据资源的属性（如果有）
                if data.get('attributes'):
                    data_info_parts.append("")
                    data_info_parts.append("Data Resource Attributes:")
                    import json
                    data_info_parts.append(json.dumps(data.get('attributes'), indent=2, ensure_ascii=False))
                
                data_info_str = "\n".join(data_info_parts)
                
                prompt_parts.extend([
                    "The following data resource is referenced by this component. Use it to understand the data structure and how to bind data.",
                    "[Data Resource]",
                    data_info_str,
                    "[/Data Resource]",
                    "",
                    "**CRITICAL: Property Names**:",
                    "- ALL data property names MUST use lowercase camelCase (e.g., `alias`, `employeeNumber`, `costCenter`, `lineItems`)",
                    "- Do NOT use PascalCase property names (e.g., `Alias`, `EmployeeNumber`, `CostCenter`)",
                    "- When accessing data properties in your component, always use lowercase property names",
                    "- Example: If the data has a property, access it as `dataResource.alias` (NOT `dataResource.Alias`)",
                    ""
                ])
        
        # 添加子组件代码（如果有）
        if child_react_code and child_react_code.strip():
            prompt_parts.extend([
                "The following child components have been migrated to React. You can reference them in your implementation.",
                "[Child Components]",
                child_react_code,
                "[/Child Components]",
                ""
            ])
        
        # 添加 MUI 文档（如果有）
        if mui_components_docs and mui_components_docs.strip():
            prompt_parts.extend([
                "The following MUI component documentation is relevant to this migration.",
                "**CRITICAL**: You MUST follow the usage examples EXACTLY - use the same imports, component structure, and props pattern shown in the examples.",
                "Use ONLY the simplest and most common APIs from the examples - do NOT use advanced features or complex configurations.",
                "[MUI Component Documentation]",
                mui_components_docs,
                "[/MUI Component Documentation]",
                ""
            ])
        
        # 添加要求
        prompt_parts.extend([
            "## Requirements",
            "",
            "Follow the Chain of Thought process outlined in the system prompt:",
            "",
            "1. **Step 1 - Analyze**: Analyze and summarize the WPF component's key attributes and layout characteristics",
            "2. **Step 2 - Select**: Use provided MUI components with their usage examples, or autonomously select suitable MUI components, or create custom React components if needed",
            "3. **Step 3 - Migrate**: Follow the simplicity principle - use minimal code, simplest logic, ignore unnecessary styles, prefer onClick for events",
            "   - **CRITICAL**: If MUI component usage examples are provided, follow them EXACTLY - use the same imports, structure, and props",
            "   - Use ONLY the simplest APIs shown in examples - avoid advanced features or complex configurations",
            "",
            "Additional requirements:",
            "- Use TypeScript for type safety",
            "- Use React version 18.2.0",
            "- Use MUI (Material-UI) version 5.18.0 - ensure all imports and API calls are compatible with this version",
            "- Use Emotion version 11.11.x",
            "- Use TypeScript version 5.9.3",
            "- Use AutoGen version 0.7.5 if any AutoGen-related code is needed",
            "- Follow React 18.2.0 and MUI v5.18.0 best practices",
            "- Preserve all business logic and functionality",
            "- Respond in the specified tag format",
            "- **CRITICAL**: Prefer using MUI standard components directly (Button, TextField, Typography, etc.) instead of creating custom wrapper components. Only create custom components when there is complex business logic or meaningful UI patterns that cannot be expressed inline.",
            "- **CRITICAL**: When MUI component usage examples are provided:",
            "  * Use the EXACT same import statements from the example",
            "  * Use the EXACT same component structure (e.g., Dialog must include DialogTitle, DialogContent, DialogActions)",
            "  * Use the EXACT same props pattern (e.g., `open` and `onClose` for Dialog)",
            "  * Use ONLY the simplest APIs shown - do NOT add advanced features or methods not in the example",
            "  * Do NOT use methods or APIs that are NOT shown in the example (e.g., don't use `getTotal()` if not in the example)",
            "- **For Dialog components**: ALWAYS wrap content in `<Dialog open={open} onClose={onClose}>` with `<DialogTitle>`, `<DialogContent>`, and optionally `<DialogActions>`",
            "- **For DataGrid**: Ensure each row has an `id` field - use simple column configuration: `{ field: 'fieldName', headerName: 'Header Name' }`",
            ""
        ])
        
        return "\n".join(prompt_parts)
