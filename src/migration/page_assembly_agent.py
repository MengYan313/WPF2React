# -*- coding: utf-8 -*-
"""
Page Assembly Agent

负责将已迁移的根组件整合成完整的 React 页面。
"""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from autogen_core import MessageContext, message_handler

from src.llm import LLMConfig
from .base import BaseMigrationAgent
from .messages import PageAssemblyRequest, PageAssemblyResponse
from .utils import extract_tag_content, inject_imports, read_file_content, log_code_output, ensure_correct_export_name, get_available_resources, get_available_migrated_files, save_tsx_file


class PageAssemblyAgent(BaseMigrationAgent):
    """
    页面整合 Agent
    
    职责：
    1. 接收已迁移的根组件代码
    2. 通过多轮渐进式修改整合成完整的 React 页面（按执行顺序）：
       - 第一轮：初始组装 - 基于根组件代码创建基本结构，组装完整页面，确保函数签名格式正确
       - 第二轮：资源修复 - 确保资源引用正确，修复资源路径问题
       - 第三轮：模板整合 - 整合根节点的模板依赖，处理模板相关逻辑（可选）
       - 第四轮：数据整合 - 整合根节点的数据依赖，处理数据访问逻辑（可选）
       - 第五轮：布局优化 - 确保整体布局正确，优化页面结构
       - 第六轮：子页面集成 - 确保子页面引用正确，集成子组件
       - 第七轮：代码规范 - 确保代码结构符合规范，最终代码优化
    3. 返回完整的页面代码
    """
    
    def __init__(
        self,
        project_name: str,
        output_base_dir: str = "outputs",
        llm_config: Optional[LLMConfig] = None
    ):
        """
        初始化页面整合 Agent
        
        Args:
            project_name: 项目名称（例如 "ExpenseItDemo"）
            output_base_dir: 输出基础目录
            llm_config: LLM 配置（默认使用 gpt-4o，非 JSON 模式）
        """
        # 初始化基类（页面整合不需要 JSON 模式）
        super().__init__(
            agent_type="PageAssemblyAgent",
            llm_config=llm_config or LLMConfig(
                model="gpt-4o",
                temperature=0,
                json_mode=False  # 页面整合必须使用纯文本模式
            ),
            output_base_dir=output_base_dir
        )
        
        # 项目配置
        self.project_name = project_name
        self.output_base_dir = Path(output_base_dir)
        
        # 目录路径
        self.dependency_dir = self.output_base_dir / project_name / "dependency"
        self.result_dir = Path("result") / project_name
        self.resources_dir = self.result_dir / "public"  # 资源文件目录
    
    @message_handler
    async def handle_assembly_request(
        self,
        message: PageAssemblyRequest,
        ctx: MessageContext
    ) -> PageAssemblyResponse:
        """
        处理页面整合请求
        
        Args:
            message: 页面整合请求消息
            ctx: 消息上下文
        
        Returns:
            页面整合响应消息
        """
        try:
            # 执行页面整合
            result = await self._assemble_page(
                page_name=message.page_name,
                page_source=message.page_source,
                root_result={
                    "react_code": message.root_component,
                    "imports": message.root_imports,
                    "interfaces": message.root_interfaces
                },
                page_layout_description=message.page_layout_description,
                child_page_references=message.child_page_references,
                direct_dependencies=message.direct_dependencies,
                template=message.template,
                data=message.data
            )
            
            return PageAssemblyResponse(
                page_code=result["page_code"],
                page_description=result["page_description"],
                assembly_notes=result["assembly_notes"]
            )
            
        except Exception as e:
            return PageAssemblyResponse(
                page_code="",
                page_description="",
                assembly_notes=f"页面整合失败: {str(e)}"
            )
    
    async def _assemble_page(
        self,
        page_name: str,
        page_source: str,
        root_result: Dict[str, Any],
        page_layout_description: str,
        child_page_references: str,
        direct_dependencies: List[str],
        template: str = "",
        data: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """
        页面整合阶段：将根组件整合成完整的 React 页面（多轮渐进式修改）
        
        Args:
            page_name: 页面名称（最终导出的组件名必须与此相同）
            page_source: 完整的 WPF 页面源代码（XAML）
            root_result: 根组件的迁移结果
            page_layout_description: 页面布局描述
            child_page_references: 子页面引用分析
            direct_dependencies: 直接依赖页面列表
            
        Returns:
            整合后的页面代码字典
        """
        from src.llm import LLMClient, LLMConfig
        
        self.logger.info(f"开始页面整合: {page_name}")
        
        temp_config = LLMConfig(
            model=self.llm_client.config.model,
            temperature=self.llm_client.config.temperature,
            json_mode=False  # 页面整合必须使用纯文本模式
        )
        temp_client = LLMClient(config=temp_config)
        
        # 获取可用的资源文件列表
        available_resources = get_available_resources(self.resources_dir)
        self.logger.debug(f"  可用资源文件: {available_resources}")
        
        # 创建临时文件路径用于存储每一轮的结果
        temp_tsx_path = self.result_dir / f"{page_name}_temp.tsx"
        
        # 提取根组件信息
        component_code = root_result.get("react_code", "")
        imports = root_result.get("imports", [])
        interfaces = root_result.get("interfaces", "")
        imports_text = "\n".join(imports) if isinstance(imports, list) else str(imports)
        
        # 获取已迁移的文件列表（用于验证可用的导入）
        available_files = get_available_migrated_files(self.result_dir)
        
        # 自动生成页面依赖的 import 语句
        page_imports = []
        if direct_dependencies:
            for dep in direct_dependencies:
                # 检查文件是否存在
                dep_file = self.result_dir / f"{dep}.tsx"
                if dep_file.exists():
                    page_imports.append(f"import {dep} from './{dep}';")
                else:
                    self.logger.warning(f"依赖页面 '{dep}' 的文件不存在: {dep_file}")
        
        # 自动生成数据依赖的 import 语句
        data_imports = []
        if data and isinstance(data, dict):
            if 'import_statement' in data:
                # 使用迁移后的数据格式
                data_imports.append(data.get('import_statement', ''))
            elif data.get('key'):
                # 原始数据格式，需要生成 import
                from .data_migrate_agent import DataMigrateAgent
                temp_agent = DataMigrateAgent(project_name=self.project_name, output_base_dir=str(self.output_base_dir))
                data_imports.append(temp_agent._generate_import_statement(data.get('key')))
        
        # 构建依赖页面导入说明（用于 prompt）
        dependency_imports_text = ""
        if direct_dependencies:
            dependency_imports_list = []
            for dep in direct_dependencies:
                dep_file = self.result_dir / f"{dep}.tsx"
                if dep_file.exists():
                    dependency_imports_list.append(f"- {dep}: Available (import already generated)")
                else:
                    dependency_imports_list.append(f"- {dep}: NOT AVAILABLE (file does not exist)")
            dependency_imports_text = "\n".join(dependency_imports_list)
        else:
            dependency_imports_text = "None"
        
        # 构建数据依赖说明（用于 prompt）
        data_dependency_text = ""
        if data and isinstance(data, dict) and len(data) > 0:
            if 'import_statement' in data:
                data_dependency_text = f"Data resource available: {data.get('key', 'N/A')} (import already generated)"
            elif data.get('key'):
                data_dependency_text = f"Data resource available: {data.get('key', 'N/A')} (import will be generated)"
        else:
            data_dependency_text = "None"
        
        # 合并所有自动生成的 import 语句
        auto_generated_imports = page_imports + data_imports
        
        # 构建资源信息部分
        resources_section = ""
        if available_resources:
            resources_list = "\n".join([f"  - {res}" for res in available_resources])
            resources_section = f"""
Available Resources (in public/ directory):
{resources_list}

Note: Reference these resources using absolute paths starting with `/`, e.g., `/Watermark.png`
"""
        else:
            resources_section = """
Available Resources: None (no resources found in public/ directory)
"""
        
        # ========== 多轮渐进式修改 ==========
        # 执行顺序：1.初始组装 2.资源修复 3.模板整合 4.数据整合 5.布局优化 6.子页面集成 7.代码规范
        
        # 在初始组装前，记录迁移后的根组件代码
        self.logger.info(f"  迁移后的根组件代码:")
        log_code_output("迁移后的根组件", page_name, component_code, self.logger)
        
        # 第一轮：初始组装 - 基于根组件代码创建基本结构，组装完整页面，确保函数签名格式正确
        self.logger.info(f"  第一轮：初始组装...")
        page_code = await self._assemble_round_1_initial(
            temp_client=temp_client,
            page_name=page_name,
            component_code=component_code,
            imports_text=imports_text,
            interfaces=interfaces,
            dependency_imports_text=dependency_imports_text,
            direct_dependencies=direct_dependencies,
            data_dependency_text=data_dependency_text,
            available_files=available_files
        )
        save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
        self.logger.info(f"  ✓ 第一轮：初始组装完成")
        log_code_output("第一轮：初始组装", page_name, page_code, self.logger)
        
        # 在第一轮之后，自动添加生成的 import 语句
        if auto_generated_imports:
            self.logger.debug(f"  自动添加 import 语句: {len(auto_generated_imports)} 条")
            page_code = inject_imports(page_code, auto_generated_imports)
            save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
            self.logger.debug(f"  ✓ 自动添加 import 语句完成")
            log_code_output("第一轮：初始组装（添加 import 后）", page_name, page_code, self.logger)
        
        # 第二轮：资源修复 - 确保资源引用正确，修复资源路径问题
        self.logger.info(f"  第二轮：资源修复...")
        page_code = await self._assemble_round_2_resources(
            temp_client=temp_client,
            page_name=page_name,
            resources_section=resources_section,
            available_resources=available_resources,
            temp_tsx_path=temp_tsx_path
        )
        save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
        self.logger.info(f"  ✓ 第二轮：资源修复完成")
        log_code_output("第二轮：资源修复", page_name, page_code, self.logger)
        
        # 第三轮：模板整合 - 整合根节点的模板依赖，处理模板相关逻辑（如果存在）
        if template and template.strip():
            self.logger.info(f"  第三轮：模板整合...")
            page_code = await self._assemble_round_3_template(
                temp_client=temp_client,
                page_name=page_name,
                template_code=template,
                temp_tsx_path=temp_tsx_path
            )
            save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
            self.logger.info(f"  ✓ 第三轮：模板整合完成")
            log_code_output("第三轮：模板整合", page_name, page_code, self.logger)
        else:
            self.logger.debug("  第三轮：模板整合（跳过：无模板依赖）")
        
        # 第四轮：数据整合 - 整合根节点的数据依赖，处理数据访问逻辑（如果存在）
        if data is None:
            data = {}
        if data and len(data) > 0:
            self.logger.info(f"  第四轮：数据整合...")
            page_code = await self._assemble_round_4_data(
                temp_client=temp_client,
                page_name=page_name,
                data_info=data,
                temp_tsx_path=temp_tsx_path
            )
            save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
            self.logger.info(f"  ✓ 第四轮：数据整合完成")
            log_code_output("第四轮：数据整合", page_name, page_code, self.logger)
        else:
            self.logger.debug("  第四轮：数据整合（跳过：无数据依赖）")
        
        # 第五轮：布局优化 - 确保整体布局正确，优化页面结构
        self.logger.info(f"  第五轮：布局优化...")
        page_code = await self._assemble_round_5_layout(
            temp_client=temp_client,
            page_name=page_name,
            page_layout_description=page_layout_description,
            temp_tsx_path=temp_tsx_path,
            direct_dependencies=direct_dependencies,
            data_dependency_text=data_dependency_text,
            available_files=available_files
        )
        save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
        self.logger.info(f"  ✓ 第五轮：布局优化完成")
        log_code_output("第五轮：布局优化", page_name, page_code, self.logger)
        
        # 第六轮：子页面集成 - 确保子页面引用正确，集成子组件
        self.logger.info(f"  第六轮：子页面集成...")
        page_code = await self._assemble_round_6_child_pages(
            temp_client=temp_client,
            page_name=page_name,
            child_page_references=child_page_references,
            dependency_imports_text=dependency_imports_text,
            direct_dependencies=direct_dependencies,
            data_dependency_text=data_dependency_text,
            available_files=available_files,
            temp_tsx_path=temp_tsx_path
        )
        save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
        self.logger.info(f"  ✓ 第六轮：子页面集成完成")
        log_code_output("第六轮：子页面集成", page_name, page_code, self.logger)
        
        # 第七轮：代码规范 - 确保代码结构符合规范，最终代码优化
        self.logger.info(f"  第七轮：代码规范...")
        page_code = await self._assemble_round_7_code_style(
            temp_client=temp_client,
            page_name=page_name,
            temp_tsx_path=temp_tsx_path
        )
        save_tsx_file(temp_tsx_path, page_code, page_name, self.logger)
        self.logger.info(f"  ✓ 第七轮：代码规范完成")
        log_code_output("第七轮：代码规范", page_name, page_code, self.logger)
        
        # 最终清理和验证
        self.logger.debug(f"  最终清理和验证...")
        page_code = ensure_correct_export_name(page_code, page_name, self.logger)
        self.logger.debug(f"  ✓ 最终清理和验证完成")
        log_code_output("最终清理和验证", page_name, page_code, self.logger)
        
        # 删除临时文件
        if temp_tsx_path.exists():
            try:
                temp_tsx_path.unlink()
                self.logger.debug(f"  ✓ 已删除临时文件: {temp_tsx_path}")
            except Exception as e:
                self.logger.warning(f"删除临时文件失败: {temp_tsx_path}, 错误: {e}")
        
        # 构建整合说明（按实际执行顺序）
        rounds_list = [
            "initial assembly",  # 第一轮
            "resource fixing",  # 第二轮
        ]
        if template and template.strip():
            rounds_list.append("template integration")  # 第三轮
        if data and len(data) > 0:
            rounds_list.append("data integration")  # 第四轮
        rounds_list.extend([
            "layout optimization",  # 第五轮
            "child page integration",  # 第六轮
            "code style"  # 第七轮
        ])
        
        rounds_text = " THEN ".join(rounds_list)
        
        self.logger.info(f"✓ 页面整合完成: {page_name} (共 {len(rounds_list)} 轮: {rounds_text})")
        
        return {
            "page_code": page_code,
            "page_description": f"Complete React page for {page_name}",
            "assembly_notes": f"Page assembled through {len(rounds_list)} rounds: {rounds_text}. Exported as {page_name}."
        }
    async def _assemble_round_1_initial(
        self,
        temp_client,
        page_name: str,
        component_code: str,
        imports_text: str,
        interfaces: str,
        dependency_imports_text: str,
        direct_dependencies: List[str] = None,
        data_dependency_text: str = "",
        available_files: List[str] = None
    ) -> str:
        """
        第一轮：初始组装 - 基于根组件代码创建基本结构，组装完整页面
        
        此轮优先执行，基于已迁移的根组件代码创建完整的页面结构。
        组装所有组件代码、导入语句和接口定义，确保页面基本结构完整。
        最重要的是确保函数签名格式正确：MainWindow 使用 `export function MainWindow()`，
        其他页面使用 `export function PageName({ open, onClose }: PageNameProps)`。
        """
        if available_files is None:
            available_files = []
        if direct_dependencies is None:
            direct_dependencies = []
        
        available_files_text = "\n".join([f"  - {f}" for f in available_files]) if available_files else "  (none)"
        
        # 判断是否是 MainWindow
        is_main_window = page_name == "MainWindow" or "main" in page_name.lower() or "window" in page_name.lower()
        
        # 根据页面类型生成函数签名要求（整合到第一轮中）
        if is_main_window:
            function_signature_section = """## CRITICAL: Function Signature Format (MUST FOLLOW)

**For MainWindow pages, you MUST use this EXACT function signature:**

```typescript
export function MainWindow() {
  // component code here
}
```

**Rules:**
- **NO props interface** - MainWindow should NOT accept any props
- **NO React.FC** - Use function declaration, not React.FC
- **Function name**: Must be exactly "MainWindow"
- **Data access**: Import data directly from `./data` (e.g., `import { expenseData, employees, costCenters } from './data';`)
- **State management**: Use `useState` ONLY for UI state (dialog open/close, form selections)
- **Data updates**: Directly modify global data objects (e.g., `expenseData.alias = value`)
- **Child dialogs**: Control using `useState` and pass `open` and `onClose` props

**Example:**
```typescript
import { useState } from 'react';
import { Button } from '@mui/material';
import { expenseData } from './data';
import ChildDialog from './ChildDialog';

export function MainWindow() {
  const [dialogOpen, setDialogOpen] = useState(false);
  
  const handleAliasChange = (value: string) => {
    expenseData.alias = value;  // Direct modification
  };
  
  return (
    <>
      <Button onClick={() => setDialogOpen(true)}>Open Dialog</Button>
      <ChildDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </>
  );
}

export default MainWindow;
```

**WRONG patterns to AVOID:**
- **DO NOT USE**: `interface Props { alias: string; onAliasChange: (value: string) => void; ... }`
- **DO NOT USE**: `const MainWindow: React.FC<Props> = ({ alias, onAliasChange, ... }) => { ... }`
- **DO NOT USE**: `export default function MainWindow(props: Props) { ... }`"""
        else:
            function_signature_section = f"""## CRITICAL: Function Signature Format (MUST FOLLOW)

**For Dialog/Modal pages, you MUST use this EXACT function signature:**

```typescript
interface {page_name}Props {{
  open: boolean;
  onClose: () => void;
}}

export function {page_name}({{ open, onClose }}: {page_name}Props) {{
  // component code here
}}
```

**Rules:**
- **Props interface**: Must define `{page_name}Props` with `open: boolean` and `onClose: () => void`
- **Function signature**: Must use destructuring `{{ open, onClose }}: {page_name}Props`
- **NO React.FC** - Use function declaration, not React.FC
- **Function name**: Must be exactly "{page_name}"
- **Parameter order**: `open` must come before `onClose`
- **MUI Dialog**: Wrap content in MUI `Dialog` component with `open` and `onClose` props
- **State management**: Use `useState` for local state within the dialog
- **Data access**: Import data directly from `./data` for reading

**Example:**
```typescript
import {{ useState }} from 'react';
import {{ Dialog, DialogTitle, DialogContent, DialogActions, Button }} from '@mui/material';
import {{ expenseData }} from './data';

interface {page_name}Props {{
  open: boolean;
  onClose: () => void;
}}

export function {page_name}({{ open, onClose }}: {page_name}Props) {{
  const [localState, setLocalState] = useState(initialValue);
  
  return (
    <Dialog open={{{{open}}}} onClose={{{{onClose}}}}>
      <DialogTitle>Title</DialogTitle>
      <DialogContent>
        <Typography>{{{{expenseData.alias}}}}</Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={{{{onClose}}}}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}}

export default {page_name};
```

**Function Signature Rules (STRICTLY ENFORCED):**
- **MUST use**: `export function {page_name}({{ open, onClose }}: {page_name}Props) {{ ... }}`
- **DO NOT use**: `export function {page_name}(props: {page_name}Props) {{ ... }}`
- **DO NOT use**: `export function {page_name}({{ open, onClose, ...otherProps }}: {page_name}Props) {{ ... }}`
- **DO NOT use**: `export const {page_name}: React.FC<{page_name}Props> = ({{ open, onClose }}) => {{ ... }}`
- **DO NOT add**: Additional parameters like `{{ open, onClose, data, handlers }}`
- **DO NOT remove**: Either `open` or `onClose` from the function signature
- The function signature is FIXED and must remain EXACTLY as shown in the example

**Data Interaction Pattern:**
- **Read data**: Import from `./data` and read directly (e.g., `expenseData.alias`)
- **Update data**: Directly modify global data objects (e.g., `expenseData.alias = newValue`)
- **Local state**: Use `useState` only for UI state (dialog open/close, form selections, temporary values)"""
        
        system_prompt = f"""You are an expert in React and TypeScript.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Assemble a migrated React component into a complete TypeScript page file with proper structure.

{function_signature_section}

## What you must do:
1. **CRITICAL**: Use the correct function signature format as specified above
2. **DO NOT generate import statements** - All necessary imports are already generated by the system
3. Put TypeScript interfaces after imports (if any)
4. Put the complete component code (with all its logic and TSX)
5. Use ONLY official React/MUI components and the listed dependencies
6. Ensure the component name matches the specified page name exactly
7. Put `export default PageName;` at the very end

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

**Important**: 
- **MANDATORY**: You MUST use the `[TypeScript Code]` and `[/TypeScript Code]` tags - DO NOT output code without these tags
- Do NOT use markdown code blocks (```)
- Do NOT include explanations or comments outside the code tags
- The code should be ready to save directly as a `.tsx` file
- If you output code without the tags, it will cause parsing errors

## Critical Rules:
- **NO JSON formatting**: Output only code, not JSON
- **NO import statements**: DO NOT generate any import statements - they are already provided
- **Preserve ALL logic**: Preserve ALL component logic and TSX from the input
- **Component name**: The component name MUST match the page_name exactly
- **Export statement**: MUST be `export default PageName;` where PageName is the exact page name
"""
        
        user_prompt = f"""Assemble this into a complete .tsx page file:

[Page Name] (must match export name)
{page_name}
[/Page Name]

[Direct Dependencies - Available Child Pages]
{dependency_imports_text}
[/Direct Dependencies - Available Child Pages]

[Data Dependencies - Available Data Resources]
{data_dependency_text}
[/Data Dependencies - Available Data Resources]

[Root Component Code]
{component_code}
[/Root Component Code]

[Root Component Imports - Already Generated]
{imports_text}
[/Root Component Imports - Already Generated]

[Root Component Interfaces]
{interfaces}
[/Root Component Interfaces]

CRITICAL REQUIREMENTS:
1. Follow the Page Component Pattern specified in the system prompt (MainWindow vs Dialog/Modal)
2. **DO NOT generate any import statements** - All imports are already generated
3. **ONLY use official React/MUI components** and listed dependencies
4. **DO NOT create or reference non-existent components**
5. Ensure component name is exactly "{page_name}" and export as `export default {page_name};`
6. Replace any references to non-existent components with appropriate React/MUI components

Output valid TypeScript code ready to save as {page_name}.tsx (WITHOUT any import statements)"""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_2_resources(
        self,
        temp_client,
        page_name: str,
        resources_section: str,
        available_resources: List[str],
        temp_tsx_path: Path
    ) -> str:
        """
        第二轮：资源修复 - 确保资源引用正确，修复资源路径问题
        
        此轮在初始组装之后执行，确保所有资源引用（如图片、静态文件）使用正确的路径格式。
        修复硬编码或占位符路径，确保资源文件能够正确加载。
        注意：不能修改函数签名格式。
        """
        current_code = read_file_content(temp_tsx_path)
        
        system_prompt = """You are an expert in React resource management.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Fix all resource references in the component code to use correct paths.

## What you must do:
1. Check for resource references (images, static files, etc.)
2. Replace hardcoded or placeholder paths with correct `/filename` format
3. Ensure image sources use `/filename.ext` format for files in public/ directory
4. Remove or fix any incorrect resource references
5. Preserve ALL existing functionality and logic
6. Do NOT change component name, imports, or export statement

## Resource Reference Guidelines:
- Use absolute paths starting with `/` for files in public/ directory
- Example: `/Watermark.png` for a file named `Watermark.png` in `public/`
- DO NOT use relative paths like `./public/filename.png`
- DO NOT use `process.env.PUBLIC_URL` unless specifically needed

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

**Important**: 
- **MANDATORY**: You MUST use the `[TypeScript Code]` and `[/TypeScript Code]` tags - DO NOT output code without these tags
- Do NOT use markdown code blocks (```)
- Do NOT include explanations or comments outside the code tags
- The code should be ready to save directly as a `.tsx` file
- If you output code without the tags, it will cause parsing errors

## Critical Rules:
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Resource only**: Only fix resource references
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        user_prompt = f"""Fix resource references in this React component:

[Page Name]
{page_name}
[/Page Name]

{resources_section}

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. Check for resource references (images, static files, etc.)
2. Replace hardcoded or placeholder paths with correct `/filename` format
3. Ensure image sources use `/filename.ext` format for files in public/ directory
4. Remove or fix any incorrect resource references
5. Preserve ALL existing functionality and logic
6. **CRITICAL**: Do NOT modify the function signature - it is already correct
7. Do NOT change component name, imports, or export statement

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_3_template(
        self,
        temp_client,
        page_name: str,
        template_code: str,
        temp_tsx_path: Path
    ) -> str:
        """
        第三轮：模板整合 - 整合根节点的模板依赖，处理模板相关逻辑
        
        此轮在资源修复之后执行，整合根节点所需的模板代码。
        理解模板结构并将其正确集成到组件中，确保模板相关的导入和逻辑正确。
        注意：不能修改函数签名格式。
        """
        current_code = read_file_content(temp_tsx_path)
        
        system_prompt = """You are an expert in React component integration.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Integrate template code into the React component.

## What you must do:
1. Understand the template structure and how it should be used
2. Integrate the template logic into the component where appropriate
3. Ensure template-related imports are added if needed
4. Preserve ALL existing functionality and logic
5. Do NOT change component name, main structure, or export statement

## Template Integration Guidelines:
- Templates (DataTemplate/ControlTemplate) define how data should be rendered
- Convert template logic to React component structure
- Use appropriate MUI components based on template content
- Ensure data binding is correctly implemented

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

**Important**: 
- **MANDATORY**: You MUST use the `[TypeScript Code]` and `[/TypeScript Code]` tags - DO NOT output code without these tags
- Do NOT use markdown code blocks (```)
- Do NOT include explanations or comments outside the code tags
- The code should be ready to save directly as a `.tsx` file
- If you output code without the tags, it will cause parsing errors

## Critical Rules:
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Template integration**: Integrate template logic appropriately
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        user_prompt = f"""Integrate the following template into this React component:

[Page Name]
{page_name}
[/Page Name]

[Template Code]
{template_code}
[/Template Code]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. Understand the template structure and how it should be used
2. Integrate the template logic into the component where appropriate
3. Ensure template-related imports are added if needed
4. Preserve ALL existing functionality and logic
5. **CRITICAL**: Do NOT modify the function signature - it is already correct
6. Do NOT change component name, main structure, or export statement

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_4_data(
        self,
        temp_client,
        page_name: str,
        data_info: Dict[str, Any],
        temp_tsx_path: Path
    ) -> str:
        """
        第四轮：数据整合 - 整合根节点的数据依赖，处理数据访问逻辑
        
        此轮在模板整合之后执行，整合根节点所需的数据资源。
        确保数据导入语句正确，数据访问逻辑符合要求，使用小写属性名访问数据。
        注意：不能修改函数签名格式。
        """
        current_code = read_file_content(temp_tsx_path)
        
        # 检查是否是迁移后的数据格式（包含 ts_code 和 import_statement）
        if 'ts_code' in data_info and 'import_statement' in data_info:
            # 使用迁移后的数据格式
            data_section = f"""[Data Resource - Import Statement]
{data_info.get('import_statement', '')}
[/Data Resource - Import Statement]

[Data Resource - TypeScript Code]
{data_info.get('ts_code', '')}
[/Data Resource - TypeScript Code]

Important:
- Use the import statement above to import the data in your component
- The TypeScript code shows the data structure and how it's defined
- Use the imported data constant directly in your component
"""
        else:
            # 使用原始 WPF 数据格式（向后兼容）
            data_info_parts = []
            data_info_parts.append(f"Data Resource Key: {data_info.get('key', 'N/A')}")
            data_info_parts.append(f"Data Resource Type: {data_info.get('data_resource_type', 'N/A')}")
            data_info_parts.append(f"Source File: {data_info.get('source_file', 'N/A')}")
            
            if data_info.get('source_code'):
                data_info_parts.append("")
                data_info_parts.append("Data Resource Source Code:")
                data_info_parts.append(data_info.get('source_code'))
            
            if data_info.get('attributes'):
                data_info_parts.append("")
                data_info_parts.append("Data Resource Attributes:")
                import json
                data_info_parts.append(json.dumps(data_info.get('attributes'), indent=2, ensure_ascii=False))
            
            data_section = "\n".join(data_info_parts)
        
        system_prompt = """You are an expert in React data integration.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Integrate data resources into the React component.

## What you must do:
1. Add the data import statement to the imports section
2. Use the imported data in the component where appropriate
3. Ensure data binding is correctly implemented
4. Preserve ALL existing functionality and logic
5. Do NOT change component name, main structure, or export statement

## Data Integration Guidelines:
- Add import statements at the top of the file
- Use the imported data constant in the component
- Ensure proper data binding and usage
- If the data is used for DataContext or similar, integrate it appropriately

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

**Important**: 
- **MANDATORY**: You MUST use the `[TypeScript Code]` and `[/TypeScript Code]` tags - DO NOT output code without these tags
- Do NOT use markdown code blocks (```)
- Do NOT include explanations or comments outside the code tags
- The code should be ready to save directly as a `.tsx` file
- If you output code without the tags, it will cause parsing errors

## Critical Rules:
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Data integration**: Integrate data import and usage appropriately
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        user_prompt = f"""Integrate the following data resource into this React component:

[Page Name]
{page_name}
[/Page Name]

{data_section}

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. Add the data import statement to the imports section
2. Use the imported data in the component where appropriate
3. Ensure data binding is correctly implemented
4. Preserve ALL existing functionality and logic
5. **CRITICAL**: Do NOT modify the function signature - it is already correct
6. Do NOT change component name, main structure, or export statement

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_5_layout(
        self,
        temp_client,
        page_name: str,
        page_layout_description: str,
        temp_tsx_path: Path,
        direct_dependencies: List[str] = None,
        data_dependency_text: str = "",
        available_files: List[str] = None
    ) -> str:
        """
        第五轮：布局优化 - 确保整体布局正确，优化页面结构
        
        此轮在数据整合之后执行，根据页面布局描述优化整体布局结构。
        确保组件布局符合原始 WPF 页面的布局要求，使用正确的 MUI 布局组件。
        注意：不能修改函数签名格式。
        """
        if direct_dependencies is None:
            direct_dependencies = []
        if available_files is None:
            available_files = []
        
        current_code = read_file_content(temp_tsx_path)
        
        system_prompt = f"""You are an expert in React and TypeScript UI layout.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Modify the existing React component to ensure the overall layout matches the provided layout description.

## What you must do:
1. **CRITICAL**: Verify the component follows the Page Component Pattern (MainWindow vs Dialog/Modal)
2. Read the current component code carefully
3. Adjust the layout structure (Grid, Stack, Box, etc.) to match the layout description
4. Ensure visual hierarchy and spatial relationships are correct
5. Preserve ALL existing functionality and logic
6. Do NOT change imports, interfaces, or component name
7. Do NOT change child page integrations (if any)
8. Replace any non-existent component references with appropriate React/MUI components

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

**Important**: 
- **MANDATORY**: You MUST use the `[TypeScript Code]` and `[/TypeScript Code]` tags - DO NOT output code without these tags
- Do NOT use markdown code blocks (```)
- Do NOT include explanations or comments outside the code tags
- The code should be ready to save directly as a `.tsx` file
- If you output code without the tags, it will cause parsing errors

## Critical Rules:
- **NO import statements**: DO NOT generate any import statements - they are already provided
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Layout only**: Only modify layout structure to match the description
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        user_prompt = f"""Modify the layout of this React component to match the layout description:

[Page Name]
{page_name}
[/Page Name]

[Page Layout Description]
{page_layout_description}
[/Page Layout Description]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. Adjust the layout structure to match the layout description
2. Ensure visual hierarchy and spatial relationships are correct
3. Preserve ALL existing functionality and logic
4. **CRITICAL**: Do NOT modify the function signature - it is already correct
5. Do NOT change imports, interfaces, or component name
6. Do NOT change child page integrations (if any)

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_6_child_pages(
        self,
        temp_client,
        page_name: str,
        child_page_references: str,
        dependency_imports_text: str,
        direct_dependencies: List[str] = None,
        data_dependency_text: str = "",
        available_files: List[str] = None,
        temp_tsx_path: Path = None
    ) -> str:
        """
        第六轮：子页面集成 - 确保子页面引用正确，集成子组件
        
        此轮在布局优化之后执行，确保所有子页面组件正确集成。
        验证子页面导入和引用，使用正确的对话框交互模式（open/onClose），处理嵌套对话框。
        注意：不能修改函数签名格式。
        """
        if direct_dependencies is None:
            direct_dependencies = []
        if available_files is None:
            available_files = []
        
        current_code = read_file_content(temp_tsx_path)
        
        # Standard dialog interaction pattern - use open/onClose props
        state_example = "const [dialogOpen, setDialogOpen] = useState(false);"
        button_example = "<Button onClick={() => setDialogOpen(true)}>Open Dialog</Button>"
        dialog_example = "<ChildDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />"
        
        system_prompt = f"""You are an expert in React and TypeScript component integration.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Integrate child page components into the parent component based on the child page references analysis.

## Page Interaction Pattern (CRITICAL):

### For MainWindow Components:
- Use `useState` to manage dialog state: `{state_example}`
- Pass `open` and `onClose` props to child dialogs: `{dialog_example}`
- Use onClick handlers: `{button_example}`

### For Dialog/Modal Components:
- Use separate `useState` for each nested dialog
- Pass `open` and `onClose` props to nested dialogs
- Wrap nested dialogs in MUI `Dialog` component

## What you must do:
1. **MANDATORY**: Import ALL child page components listed in Direct Dependencies
2. **MANDATORY**: Use ALL imported child page components in the TSX code
3. **Dialog pattern**: Use `useState` for dialog state, pass `open` and `onClose` props
4. **MUI Dialog**: Wrap dialog components in MUI `Dialog` component (if not already wrapped)
5. Use onClick handlers to control when child pages are shown/hidden
6. Preserve ALL existing functionality and layout
7. Do NOT change component name or export statement

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

**Important**: 
- **MANDATORY**: You MUST use the `[TypeScript Code]` and `[/TypeScript Code]` tags - DO NOT output code without these tags
- Do NOT use markdown code blocks (```)
- Do NOT include explanations or comments outside the code tags
- The code should be ready to save directly as a `.tsx` file
- If you output code without the tags, it will cause parsing errors

## Critical Rules:
- **CRITICAL**: Every imported child page component MUST appear in the TSX code
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Keep unchanged**: Keep the component name, function signature, and export statement unchanged
"""
        
        user_prompt = f"""Integrate child page components into this React component:

[Page Name]
{page_name}
[/Page Name]

[Direct Dependencies]
{dependency_imports_text}
[/Direct Dependencies]

[Child Page References]
{child_page_references}
[/Child Page References]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. **MANDATORY**: Import ALL child page components listed in Direct Dependencies
2. **MANDATORY**: Use ALL imported child page components in the TSX code
3. Follow the Page Interaction Pattern from system prompt:
   - MainWindow: Use `useState` for dialog state, pass `open` and `onClose` props
   - Dialog: Use separate `useState` for nested dialogs
4. Example integration:
   a) Define state: `{state_example}`
   b) Add onClick handler: `{button_example}`
   c) Use dialog in TSX: `{dialog_example}`
5. Preserve ALL existing functionality and layout
6. **CRITICAL**: Do NOT modify the function signature - it is already correct
7. Do NOT change component name or export statement

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
    
    async def _assemble_round_7_code_style(
        self,
        temp_client,
        page_name: str,
        temp_tsx_path: Path
    ) -> str:
        """
        第七轮：代码规范 - 确保代码结构符合规范，最终代码优化
        
        此轮在初始组装之后执行，作为最后一轮优化，确保代码符合最佳实践。
        验证组件模式、组织导入顺序、确保代码结构规范，进行最终的代码质量检查。
        """
        current_code = read_file_content(temp_tsx_path)
        
        system_prompt = f"""You are an expert in React and TypeScript code style and best practices.

## Version Requirements
- **React**: Use version 18.2.0
- **MUI (Material-UI)**: Use version 5.18.0
- **Emotion**: Use version 11.11.x
- **TypeScript**: Use version 5.9.3
- Ensure all imports and API usage are compatible with these specific versions

Your task: Ensure the code structure follows best practices and coding standards.

## Code Structure Requirements:
1. **Imports** - All imports at the top, organized:
   - React imports first
   - MUI imports second
   - Child page component imports third
   - Data imports from './data' fourth
   - Other third-party imports last
   - Deduplicate imports
2. **Utility Functions** - If any utility functions exist, place them before the component definition
3. **Interfaces/Types** - After imports, before utility functions or component
4. **Component** - The main component code
5. **Export** - `export default PageName;` at the very end

## Code Style Requirements:
- Use onClick handlers for all event bindings (prefer onClick over other event handlers)
- Write utility functions, validators, and converters directly in the TSX file (do NOT import from non-existent files)
- Prefer MUI standard components over custom wrappers
- Use proper TypeScript typing
- Clean, readable code with proper formatting

## Output Format

**CRITICAL - Output Format**: You MUST wrap your TypeScript code in `[TypeScript Code]` and `[/TypeScript Code]` tags.

**REQUIRED FORMAT:**
[TypeScript Code]
// Your TypeScript code here
[/TypeScript Code]

**Important**: 
- **MANDATORY**: You MUST use the `[TypeScript Code]` and `[/TypeScript Code]` tags - DO NOT output code without these tags
- Do NOT use markdown code blocks (```)
- Do NOT include explanations or comments outside the code tags
- The code should be ready to save directly as a `.tsx` file
- If you output code without the tags, it will cause parsing errors

## Critical Rules:
- **Preserve ALL logic**: Preserve ALL component logic and functionality
- **Code structure**: Ensure proper structure: imports THEN interfaces THEN utility functions THEN component THEN export
- **DO NOT modify function signature**: The function signature format is already correct and must NOT be changed
- **Component name**: MUST match the page_name exactly
- **Export statement**: MUST be `export default PageName;` where PageName is the exact page name
- **MUI version**: Ensure all MUI imports and API calls are compatible with MUI v5.18.0
"""
        
        user_prompt = f"""Ensure this React component follows code style and structure best practices:

[Page Name]
{page_name}
[/Page Name]

[Current Component Code]
{current_code}
[/Current Component Code]

Requirements:
1. **CRITICAL**: Verify the component follows the Page Component Pattern (MainWindow vs Dialog/Modal)
2. **CRITICAL**: Do NOT modify the function signature - it is already correct
3. Organize imports properly (React THEN MUI THEN Child pages THEN Data THEN Others THEN Utilities)
4. Place utility functions before the component definition (if any)
5. Place interfaces after imports
6. Ensure proper code structure: imports THEN interfaces THEN utility functions THEN component THEN export
7. Use onClick handlers for all event bindings
8. Write utility functions directly in the file (do NOT import from non-existent files)
9. Ensure the component name is exactly "{page_name}" and export as `export default {page_name};`
10. Preserve ALL existing functionality and logic

Output the modified TypeScript code."""
        
        response = await temp_client.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取标记内的代码（直接使用 utils 工具）
        # 只提取 TypeScript Code 标记
        result = extract_tag_content(response, "TypeScript Code", "", self.logger)
        if not result or result == response.strip():
            # 如果未找到标记，记录错误
            self.logger.error(f"严格解析失败：无法从 LLM 响应中找到 [TypeScript Code] 标记。完整响应:\n{response}")
            return ""
        return result
